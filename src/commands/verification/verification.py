from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import quote_plus
import uuid

import re
import unicodedata
import discord

from src.services.application_store import (
    APPLICATION_STATUS_APPROVED,
    APPLICATION_STATUS_BANNED,
    APPLICATION_STATUS_CANCELLED,
    APPLICATION_STATUS_KICKED,
    APPLICATION_STATUS_LEFT,
    APPLICATION_STATUS_PENDING,
    APPLICATION_STATUS_REJECTED,
    ApplicationStore,
    StoredApplication,
)
from src.services.dm_template_store import (
    DM_TEMPLATE_APPROVED,
    DM_TEMPLATE_BANNED,
    DM_TEMPLATE_DENIED,
    DM_TEMPLATE_KICKED,
    DM_TEMPLATE_QUESTIONING,
    DEFAULT_DM_TEMPLATES,
    DmTemplateStore,
    render_template_text,
)
from src.services.forms.form_store import (
    FORM_KEY_VERIFICATION,
    FormStore,
    get_default_verification_form_config,
)
from src.services.invite_tracker import InviteTrackerStore, TrackedInviteInfo
from src.utils.form_builder import FormAnswer, build_form_modal


VERIFICATION_FORM_PATH = "data/forms/verification.json"
INTERNAL_THREAD_PREFIX = "//"


@dataclass
class VerificationSession:
    user_id: int
    guild_id: int | None
    answers: list[FormAnswer] = field(default_factory=list)


VERIFICATION_SESSIONS: dict[str, VerificationSession] = {}


def get_application_store(client: discord.Client) -> ApplicationStore | None:
    return getattr(client, "application_store", None)


def get_form_store(client: discord.Client) -> FormStore | None:
    return getattr(client, "form_store", None)


def get_dm_template_store(client: discord.Client) -> DmTemplateStore | None:
    return getattr(client, "dm_template_store", None)


def get_invite_tracker_store(client: discord.Client) -> InviteTrackerStore | None:
    return getattr(client, "invite_tracker", None)


async def load_verification_form(
    client: discord.Client,
    guild_id: int | None,
):
    form_store = get_form_store(client)

    if guild_id is not None and form_store is not None:
        form_key = FORM_KEY_VERIFICATION
        settings_store = getattr(client, "guild_settings", None)

        if settings_store is not None:
            get_form_key = getattr(settings_store, "get_verification_form_key", None)

            if get_form_key is not None:
                configured_form_key = get_form_key(guild_id)

                if configured_form_key:
                    form_key = configured_form_key

        return await form_store.get_form_config(
            guild_id=guild_id,
            form_key=form_key,
            fallback_json_path=VERIFICATION_FORM_PATH,
        )

    return get_default_verification_form_config()


def discord_timestamp(value: datetime, style: str = "R") -> str:
    return f"<t:{int(value.timestamp())}:{style}>"


def trim_embed_value(value: str, limit: int = 1000) -> str:
    cleaned = value.strip()

    if not cleaned:
        return "*No answer provided.*"

    if len(cleaned) <= limit:
        return cleaned

    return cleaned[: limit - 3] + "..."


def trim_message_content(value: str, limit: int = 1800) -> str:
    cleaned = value.strip()

    if len(cleaned) <= limit:
        return cleaned

    return cleaned[: limit - 3] + "..."


def get_avatar_reverse_search_url(user: discord.User | discord.Member) -> str:
    avatar_url = user.display_avatar.with_size(1024).url
    return f"https://lens.google.com/uploadbyurl?url={quote_plus(avatar_url)}"


def format_invite_text(invite_info: TrackedInviteInfo | None) -> str | None:
    if invite_info is None:
        return None

    if invite_info.invite_code is None:
        return "`Unknown invite`"

    invite_link = invite_info.invite_url or f"https://discord.gg/{invite_info.invite_code}"
    inviter_text = "Unknown inviter"

    if invite_info.inviter_id is not None:
        inviter_text = f"<@{invite_info.inviter_id}>"
    elif invite_info.inviter_name:
        inviter_text = discord.utils.escape_markdown(invite_info.inviter_name)

    uses_text = f" - `{invite_info.uses}` use(s)" if invite_info.uses is not None else ""

    return f"[{invite_info.invite_code}]({invite_link}) by {inviter_text}{uses_text}"


async def get_invite_text_for_user(
    client: discord.Client,
    guild_id: int,
    user_id: int,
) -> str | None:
    invite_tracker = get_invite_tracker_store(client)

    if invite_tracker is None:
        return None

    invite_info = await invite_tracker.get_member_invite_info(
        guild_id=guild_id,
        user_id=user_id,
    )

    return format_invite_text(invite_info)


ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
WHITESPACE_RE = re.compile(r"\s+")
URL_RE = re.compile(r"https?://\S+|discord\.gg/\S+", re.IGNORECASE)

# Single-word terms shorter than this will not autoban.
# This prevents very short fragments causing stupid false positives.
AUTOMOD_MIN_SINGLE_WORD_LENGTH = 3


def normalise_automod_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = ZERO_WIDTH_RE.sub("", value)
    value = URL_RE.sub(" ", value)

    value = value.replace("’", "'")
    value = value.replace("‘", "'")
    value = value.replace("`", "'")
    value = value.replace("“", '"')
    value = value.replace("”", '"')

    value = value.casefold()
    value = WHITESPACE_RE.sub(" ", value)

    return value.strip()


def application_answers_text(answers: list[FormAnswer]) -> str:
    return normalise_automod_text(
        " ".join(answer.value for answer in answers if answer.value)
    )


def normalise_automod_term(term: str) -> str:
    return normalise_automod_text(term)


def is_automod_phrase(term: str) -> bool:
    return " " in term.strip()


def build_single_word_pattern(term: str) -> re.Pattern[str] | None:
    cleaned = normalise_automod_term(term)

    if not cleaned:
        return None

    if len(cleaned) < AUTOMOD_MIN_SINGLE_WORD_LENGTH:
        return None

    # Whole-word-ish match.
    # This avoids matching the term inside longer innocent words.
    return re.compile(
        rf"(?<!\w){re.escape(cleaned)}(?!\w)",
        re.IGNORECASE,
    )


def build_phrase_pattern(term: str) -> re.Pattern[str] | None:
    cleaned = normalise_automod_term(term)

    if not cleaned:
        return None

    parts = [
        part
        for part in cleaned.split(" ")
        if part.strip()
    ]

    if len(parts) < 2:
        return build_single_word_pattern(cleaned)

    # Allows spaces/punctuation between phrase words:
    # "bad phrase"
    # "bad    phrase"
    # "bad-phrase"
    # "bad.phrase"
    #
    # But it does NOT match "badphrase", because that would be too aggressive.
    separator = r"[\s\W_]+"
    pattern_text = separator.join(re.escape(part) for part in parts)

    return re.compile(
        rf"(?<!\w){pattern_text}(?!\w)",
        re.IGNORECASE,
    )


def automod_term_matches(term: str, answers_text: str) -> bool:
    cleaned = normalise_automod_term(term)

    if not cleaned:
        return False

    if is_automod_phrase(cleaned):
        pattern = build_phrase_pattern(cleaned)
    else:
        pattern = build_single_word_pattern(cleaned)

    if pattern is None:
        return False

    return pattern.search(answers_text) is not None


def find_automod_match(
    answers: list[FormAnswer],
    terms: list[str],
) -> str | None:
    answers_text = application_answers_text(answers)

    for term in terms:
        cleaned = normalise_automod_term(term)

        if not cleaned:
            continue

        if automod_term_matches(cleaned, answers_text):
            return cleaned

    return None

async def ban_user_for_automod(
    client: discord.Client,
    guild_id: int,
    user_id: int,
    reason: str,
) -> tuple[bool, str | None]:
    guild = client.get_guild(guild_id)

    if guild is None:
        return False, "Could not find the server."

    try:
        await guild.ban(
            discord.Object(id=user_id),
            reason=reason,
        )
        return True, None
    except discord.Forbidden:
        return False, "I do not have permission to ban that user."
    except discord.HTTPException:
        return False, "Discord refused the ban request."


async def apply_approval_roles(
    client: discord.Client,
    application: StoredApplication,
) -> list[str]:
    settings_store = getattr(client, "guild_settings", None)

    if settings_store is None:
        return []

    guild = client.get_guild(application.guild_id)

    if guild is None:
        return ["Could not find the server to update roles."]

    member = guild.get_member(application.user_id)

    if member is None:
        try:
            member = await guild.fetch_member(application.user_id)
        except discord.HTTPException:
            return ["Could not find the member to update roles."]

    failures: list[str] = []
    add_role_id = settings_store.get_approved_add_role_id(application.guild_id)
    remove_role_id = settings_store.get_approved_remove_role_id(application.guild_id)

    if add_role_id is not None:
        role = guild.get_role(add_role_id)

        if role is None:
            failures.append("Approved add-role no longer exists.")
        else:
            try:
                await member.add_roles(role, reason="Verification approved")
            except discord.Forbidden:
                failures.append(f"I cannot add {role.mention} due to role hierarchy/permissions.")
            except discord.HTTPException:
                failures.append(f"Discord refused adding {role.mention}.")

    if remove_role_id is not None:
        role = guild.get_role(remove_role_id)

        if role is None:
            failures.append("Approved remove-role no longer exists.")
        else:
            try:
                await member.remove_roles(role, reason="Verification approved")
            except discord.Forbidden:
                failures.append(f"I cannot remove {role.mention} due to role hierarchy/permissions.")
            except discord.HTTPException:
                failures.append(f"Discord refused removing {role.mention}.")

    return failures


def get_questioning_thread_url(guild_id: int, thread_id: int | None) -> str | None:
    if thread_id is None:
        return None

    return f"https://discord.com/channels/{guild_id}/{thread_id}"


def build_application_review_embeds(
    application_id: str,
    user: discord.User | discord.Member,
    answers: list[FormAnswer],
    previous_application_links: list[str] | None = None,
    questioning_thread_url: str | None = None,
    invite_text: str | None = None,
) -> list[discord.Embed]:
    embeds: list[discord.Embed] = []

    display_name = getattr(user, "display_name", user.name)
    profile_url = f"https://discord.com/users/{user.id}"
    reverse_search_url = get_avatar_reverse_search_url(user)

    first_embed = discord.Embed(
        title="Verification Application",
        colour=discord.Colour.blurple(),
    )

    first_embed.set_author(
        name=str(user),
        icon_url=user.display_avatar.url,
    )

    first_embed.set_thumbnail(url=user.display_avatar.with_size(256).url)

    first_embed.add_field(
        name=f"{user.mention}'s Info:",
        value=(
            f"[View Profile]({profile_url})\n"
            f"**Display Name:** {discord.utils.escape_markdown(display_name)}\n"
            f"**Account ID:** `{user.id}`\n"
            f"**Account Created:** {discord_timestamp(user.created_at)}\n"
            f"**Invite Link:** {invite_text or '`Not tracked yet`'}\n"
            f"[Reverse Image Search Avatar]({reverse_search_url})"
        ),
        inline=False,
    )

    field_count = 1

    if previous_application_links:
        first_embed.add_field(
            name="Previous Application(s):",
            value="\n".join(previous_application_links),
            inline=False,
        )

        field_count += 1

    embeds.append(first_embed)
    current_embed = first_embed

    for answer in answers:
        if field_count >= 25:
            current_embed = discord.Embed(
                title="Verification Application Continued",
                colour=discord.Colour.blurple(),
            )

            current_embed.set_author(
                name=str(user),
                icon_url=user.display_avatar.url,
            )

            current_embed.set_thumbnail(url=user.display_avatar.with_size(256).url)

            embeds.append(current_embed)
            field_count = 0

        current_embed.add_field(
            name=answer.label[:256],
            value=trim_embed_value(answer.value),
            inline=True,
        )

        field_count += 1

    if questioning_thread_url:
        if field_count >= 25:
            current_embed = discord.Embed(
                title="Verification Application Continued",
                colour=discord.Colour.blurple(),
            )

            current_embed.set_author(
                name=str(user),
                icon_url=user.display_avatar.url,
            )

            current_embed.set_thumbnail(url=user.display_avatar.with_size(256).url)

            embeds.append(current_embed)
            field_count = 0

        current_embed.add_field(
            name="Questioning:",
            value=f"[View Thread]({questioning_thread_url})",
            inline=False,
        )

    return embeds[:10]

def get_log_colour_for_status(status: str) -> discord.Colour:
    cleaned = status.lower().strip()

    if cleaned == "approved":
        return discord.Colour.green()

    if cleaned == "denied":
        return discord.Colour.orange()

    if cleaned == "kicked":
        return discord.Colour.red()

    if cleaned == "banned":
        return discord.Colour.dark_red()
    
    if cleaned == "left":
        return discord.Colour.dark_grey()

    return discord.Colour.blurple()


def should_show_log_reason(status: str, reason: str | None) -> bool:
    if reason is None or not reason.strip():
        return False

    return status.lower().strip() in {
        "denied",
        "kicked",
        "banned",
    }


def format_reason_codeblock(reason: str, limit: int = 1000) -> str:
    cleaned = reason.strip().replace("```", "'''")

    if len(cleaned) <= limit:
        return f"```{cleaned}```"

    return f"```{cleaned[: limit - 3]}...```"


def build_application_log_embeds(
    application_id: str,
    user: discord.User | discord.Member,
    answers: list[FormAnswer],
    status: str,
    moderator: discord.User | discord.Member,
    reason: str | None = None,
    dm_sent: bool | None = None,
    questioning_thread_url: str | None = None,
    invite_text: str | None = None,
) -> list[discord.Embed]:
    embeds: list[discord.Embed] = []

    log_colour = get_log_colour_for_status(status)

    first_embed = discord.Embed(
        title=f"Verification Application {status}",
        colour=log_colour,
    )

    first_embed.set_author(
        name=str(user),
        icon_url=user.display_avatar.url,
    )

    first_embed.set_thumbnail(url=user.display_avatar.with_size(256).url)

    first_embed.add_field(
        name="User",
        value=f"{user.mention}\n`{user.id}`",
        inline=False,
    )

    first_embed.add_field(
        name="Actioned By",
        value=f"{moderator.mention}\n`{moderator.id}`",
        inline=False,
    )

    if invite_text:
        first_embed.add_field(
            name="Invite",
            value=invite_text,
            inline=False,
        )

    if status.lower().strip() == "left":
        first_embed.add_field(
            name="Result",
            value="User left the server before this application was actioned.",
            inline=False,
        )

    if questioning_thread_url:
        first_embed.add_field(
            name="Questioning Thread",
            value=f"[View Thread]({questioning_thread_url})",
            inline=False,
        )

    first_embed.set_footer(
        text=f"User ID: {user.id} | Application ID: {application_id}"
    )

    embeds.append(first_embed)
    current_embed = first_embed
    field_count = len(first_embed.fields)

    for answer in answers:
        if field_count >= 25:
            current_embed = discord.Embed(
                title=f"Verification Application {status} Continued",
                colour=log_colour,
            )

            current_embed.set_author(
                name=str(user),
                icon_url=user.display_avatar.url,
            )

            current_embed.set_thumbnail(url=user.display_avatar.with_size(256).url)

            embeds.append(current_embed)
            field_count = 0

        current_embed.add_field(
            name=answer.label[:256],
            value=trim_embed_value(answer.value),
            inline=True,
        )

        field_count += 1

    if should_show_log_reason(status, reason):
        if field_count >= 25:
            current_embed = discord.Embed(
                title=f"Verification Application {status} Continued",
                colour=log_colour,
            )

            current_embed.set_author(
                name=str(user),
                icon_url=user.display_avatar.url,
            )

            current_embed.set_thumbnail(url=user.display_avatar.with_size(256).url)

            embeds.append(current_embed)
            field_count = 0

        current_embed.add_field(
            name="Reason",
            value=format_reason_codeblock(reason or ""),
            inline=False,
        )

    return embeds[:10]


async def fetch_user_safely(
    client: discord.Client,
    user_id: int,
) -> discord.User | None:
    user = client.get_user(user_id)

    if user is not None:
        return user

    try:
        return await client.fetch_user(user_id)

    except discord.HTTPException:
        return None


async def try_dm_user(
    client: discord.Client,
    user_id: int,
    message: str,
) -> bool:
    user = await fetch_user_safely(client, user_id)

    if user is None:
        return False

    try:
        await user.send(
            message,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return True

    except discord.Forbidden:
        return False

    except discord.HTTPException:
        return False
    

def build_question_controls_embed(
    application: StoredApplication,
    applicant: discord.User | discord.Member,
    opened_by: discord.User | discord.Member,
) -> discord.Embed:
    embed = discord.Embed(
        title="Questioning Opened",
        description=(
            "Use this thread to question the applicant.\n\n"
            "**Messages sent in this thread will be forwarded to the applicant's DMs.**"
        ),
        colour=discord.Colour.blurple(),
    )

    embed.add_field(
        name="Applicant",
        value=f"{applicant.mention} (`{applicant.id}`)",
        inline=False,
    )

    embed.add_field(
        name="Opened By",
        value=f"{opened_by.mention} (`{opened_by.id}`)",
        inline=False,
    )

    embed.add_field(
        name="Start a message with `//` to keep it private.\n",
        value=(
            "Example: `// this answer seems suspicious`"
        ),
        inline=False,
    )
    

    return embed


async def log_application(
    client: discord.Client,
    application: StoredApplication,
    status: str,
    moderator: discord.User | discord.Member,
    reason: str | None = None,
    dm_sent: bool | None = None,
) -> discord.Message | None:
    settings_store = getattr(client, "guild_settings", None)

    if settings_store is None:
        return None

    get_log_channel_id = getattr(settings_store, "get_application_log_channel_id", None)

    if get_log_channel_id is None:
        return None

    log_channel_id = get_log_channel_id(application.guild_id)

    if log_channel_id is None:
        return None

    channel = client.get_channel(log_channel_id)

    if channel is None:
        try:
            channel = await client.fetch_channel(log_channel_id)
        except discord.HTTPException:
            return None

    if not isinstance(channel, discord.TextChannel):
        return None

    user = await fetch_user_safely(client, application.user_id)

    if user is None:
        return None

    invite_text = await get_invite_text_for_user(
        client=client,
        guild_id=application.guild_id,
        user_id=application.user_id,
    )

    embeds = build_application_log_embeds(
        application_id=application.id,
        user=user,
        answers=application.answers,
        status=status,
        moderator=moderator,
        reason=reason,
        dm_sent=dm_sent,
        questioning_thread_url=application.questioning_thread_url,
        invite_text=invite_text,
    )

    try:
        return await channel.send(embeds=embeds)

    except discord.HTTPException:
        return None


async def fetch_review_message(
    client: discord.Client,
    application: StoredApplication,
) -> discord.Message | None:
    if application.review_channel_id is None or application.review_message_id is None:
        return None

    channel = client.get_channel(application.review_channel_id)

    if channel is None:
        try:
            channel = await client.fetch_channel(application.review_channel_id)
        except discord.HTTPException:
            return None

    if not isinstance(channel, discord.TextChannel):
        return None

    try:
        return await channel.fetch_message(application.review_message_id)

    except discord.NotFound:
        return None

    except discord.Forbidden:
        return None

    except discord.HTTPException:
        return None


async def delete_review_message(
    client: discord.Client,
    application: StoredApplication,
) -> None:
    message = await fetch_review_message(client, application)

    if message is None:
        return

    try:
        await message.delete()

    except discord.NotFound:
        pass

    except discord.Forbidden:
        pass

    except discord.HTTPException:
        pass


async def fetch_question_thread(
    client: discord.Client,
    thread_id: int | None,
) -> discord.Thread | None:
    if thread_id is None:
        return None

    channel = client.get_channel(thread_id)

    if channel is None:
        try:
            channel = await client.fetch_channel(thread_id)
        except discord.HTTPException:
            return None

    if not isinstance(channel, discord.Thread):
        return None

    return channel


async def archive_question_thread(
    client: discord.Client,
    application: StoredApplication,
    final_status: str,
) -> None:
    thread = await fetch_question_thread(client, application.questioning_thread_id)

    if thread is None:
        return

    try:
        await thread.send(
            f"Questioning closed. Final result: **{discord.utils.escape_markdown(final_status)}**.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException:
        pass

    # Locking stops normal users from reopening/sending.
    # Archiving closes it so it disappears from the active channel/thread list.
    try:
        await thread.edit(
            locked=True,
            archived=True,
            reason=f"Verification questioning closed: {final_status}",
        )
        return

    except discord.Forbidden:
        try:
            await thread.send(
                "I tried to lock/archive this thread, but I do not have `Manage Threads`.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            pass
        return

    except discord.HTTPException:
        pass

    # Fallback: if locking failed for some Discord nonsense reason, still try to close it.
    try:
        await thread.edit(
            archived=True,
            reason=f"Verification questioning closed: {final_status}",
        )
    except discord.HTTPException:
        pass


async def update_review_message_with_question_link(
    client: discord.Client,
    application: StoredApplication,
    thread: discord.Thread,
) -> None:
    message = await fetch_review_message(client, application)

    if message is None:
        return

    user = await fetch_user_safely(client, application.user_id)

    if user is None:
        return

    application_store = get_application_store(client)
    previous_application_links: list[str] = []

    if application_store is not None:
        previous_application_links = await application_store.get_previous_application_links(
            guild_id=application.guild_id,
            user_id=application.user_id,
            exclude_application_id=application.id,
            limit=5,
        )

    invite_text = await get_invite_text_for_user(
        client=client,
        guild_id=application.guild_id,
        user_id=application.user_id,
    )

    embeds = build_application_review_embeds(
        application_id=application.id,
        user=user,
        answers=application.answers,
        previous_application_links=previous_application_links,
        questioning_thread_url=thread.jump_url,
        invite_text=invite_text,
    )

    try:
        await message.edit(
            embeds=embeds,
            view=DisabledApplicationReviewView(application.id),
        )
    except discord.HTTPException:
        pass


async def disable_review_message_actions(
    client: discord.Client,
    application: StoredApplication,
) -> None:
    message = await fetch_review_message(client, application)

    if message is None:
        return

    try:
        await message.edit(
            view=DisabledApplicationReviewView(application.id),
        )
    except discord.HTTPException:
        pass


async def post_original_application_in_thread(
    thread: discord.Thread,
    application: StoredApplication,
    user: discord.User,
) -> None:
    embeds = build_application_review_embeds(
        application_id=application.id,
        user=user,
        answers=application.answers,
        questioning_thread_url=thread.jump_url,
    )

    await thread.send(
        content="Original verification application:",
        embeds=embeds,
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def build_forward_files(message: discord.Message) -> tuple[list[discord.File], list[str]]:
    files: list[discord.File] = []
    urls: list[str] = []

    for attachment in message.attachments[:10]:
        urls.append(attachment.url)

        try:
            files.append(await attachment.to_file())
        except discord.HTTPException:
            pass

    for sticker in message.stickers:
        sticker_url = getattr(sticker, "url", None)

        if sticker_url:
            urls.append(str(sticker_url))

    return files, urls


def close_files(files: list[discord.File]) -> None:
    for file in files:
        try:
            file.close()
        except Exception:
            pass


async def send_forwarded_message(
    destination: discord.abc.Messageable,
    content: str,
    files: list[discord.File],
    fallback_urls: list[str],
    embeds: list[discord.Embed] | None = None,
) -> bool:
    embeds = embeds or []

    try:
        await destination.send(
            content=content[:2000],
            files=files,
            embeds=embeds[:10],
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return True

    except discord.HTTPException:
        close_files(files)

        fallback_content = content

        if fallback_urls:
            fallback_content = (
                f"{fallback_content}\n\n"
                "Attachment/sticker link(s):\n"
                + "\n".join(fallback_urls[:10])
            )

        try:
            await destination.send(
                content=fallback_content[:2000],
                embeds=embeds[:10],
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return True

        except discord.HTTPException:
            return False


async def forward_thread_message_to_user(
    client: discord.Client,
    message: discord.Message,
    application: StoredApplication,
) -> bool:
    user = await fetch_user_safely(client, application.user_id)

    if user is None:
        return False

    author_name = str(message.author)

    if isinstance(message.author, discord.Member):
        author_name = message.author.display_name

    if message.author.bot:
        author_name = f"{author_name} [bot]"

    body = trim_message_content(message.content)

    if body:
        content = f"**{discord.utils.escape_markdown(author_name)}:**\n{body}"
    else:
        content = f"**{discord.utils.escape_markdown(author_name)}** sent a message."

    files, urls = await build_forward_files(message)

    try:
        return await send_forwarded_message(
            destination=user,
            content=content,
            files=files,
            fallback_urls=urls,
            embeds=message.embeds,
        )
    finally:
        close_files(files)


async def forward_user_dm_to_thread(
    client: discord.Client,
    message: discord.Message,
    application: StoredApplication,
) -> bool:
    thread = await fetch_question_thread(client, application.questioning_thread_id)

    if thread is None:
        return False

    body = trim_message_content(message.content)
    author_name = str(message.author)

    if body:
        content = f"**Reply from {discord.utils.escape_markdown(author_name)}:**\n{body}"
    else:
        content = f"**Reply from {discord.utils.escape_markdown(author_name)}**"

    files, urls = await build_forward_files(message)

    try:
        return await send_forwarded_message(
            destination=thread,
            content=content,
            files=files,
            fallback_urls=urls,
            embeds=message.embeds,
        )
    finally:
        close_files(files)


async def handle_question_bridge_message(
    client: discord.Client,
    message: discord.Message,
) -> bool:
    if client.user is not None and message.author.id == client.user.id:
        return True

    application_store = get_application_store(client)

    if application_store is None:
        return False

    if isinstance(message.channel, discord.Thread):
        application = await application_store.get_pending_application_by_questioning_thread(
            message.channel.id,
        )

        if application is None:
            return False

        if message.content.startswith(INTERNAL_THREAD_PREFIX):
            return True

        await forward_thread_message_to_user(
            client=client,
            message=message,
            application=application,
        )
        return True

    if isinstance(message.channel, discord.DMChannel):
        application = await application_store.get_active_questioning_application_for_user(
            message.author.id,
        )

        if application is None:
            return False

        await forward_user_dm_to_thread(
            client=client,
            message=message,
            application=application,
        )
        return True

    return False


async def handle_verify_page_submit(
    interaction: discord.Interaction,
    session_id: str,
    page_index: int,
    answers: list[FormAnswer],
) -> None:
    session = VERIFICATION_SESSIONS.get(session_id)

    if session is None:
        await interaction.response.send_message(
            "This verification session has expired. Please press Verify again.",
            ephemeral=True,
        )
        return

    if interaction.user.id != session.user_id:
        await interaction.response.send_message(
            "This is not your verification form.",
            ephemeral=True,
        )
        return

    form = await load_verification_form(
        client=interaction.client,
        guild_id=session.guild_id,
    )
    pages = form.pages()

    total_pages = len(pages)

    session.answers.extend(answers)

    next_page_index = page_index + 1

    if next_page_index < total_pages:
        await interaction.response.send_message(
            f"Page {page_index + 1}/{total_pages} saved. Continue to the next page.",
            view=ContinueVerificationView(
                session_id=session_id,
                page_index=next_page_index,
            ),
            ephemeral=True,
        )
        return

    completed_answers = session.answers
    del VERIFICATION_SESSIONS[session_id]

    await handle_verify_complete(
        interaction=interaction,
        answers=completed_answers,
    )


async def build_verify_page_modal(
    client: discord.Client,
    guild_id: int | None,
    session_id: str,
    page_index: int,
) -> discord.ui.Modal:
    form = await load_verification_form(
        client=client,
        guild_id=guild_id,
    )
    pages = form.pages()
    total_pages = len(pages)

    if page_index < 0 or page_index >= total_pages:
        raise ValueError(f"Invalid verification form page: {page_index}")

    page_questions = pages[page_index]

    page_suffix = f" {page_index + 1}/{total_pages}"
    max_base_title_length = 45 - len(page_suffix)
    title = f"{form.title[:max_base_title_length]}{page_suffix}"

    async def on_submit(
        interaction: discord.Interaction,
        answers: list[FormAnswer],
    ) -> None:
        await handle_verify_page_submit(
            interaction=interaction,
            session_id=session_id,
            page_index=page_index,
            answers=answers,
        )

    return build_form_modal(
        title=title,
        custom_id=f"{form.custom_id_prefix}:{session_id}:{page_index}",
        questions=page_questions,
        on_submit=on_submit,
    )


class ContinueVerificationView(discord.ui.View):
    def __init__(
        self,
        session_id: str,
        page_index: int,
    ) -> None:
        super().__init__(timeout=600)

        self.session_id = session_id
        self.page_index = page_index

    @discord.ui.button(
        label="Continue",
        style=discord.ButtonStyle.primary,
        custom_id="verify:continue",
    )
    async def continue_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        session = VERIFICATION_SESSIONS.get(self.session_id)

        if session is None:
            await interaction.response.send_message(
                "This verification session has expired. Please press Verify again to restart.",
                ephemeral=True,
            )
            return

        if interaction.user.id != session.user_id:
            await interaction.response.send_message(
                "This is not your verification form.",
                ephemeral=True,
            )
            return

        modal = await build_verify_page_modal(
            client=interaction.client,
            guild_id=session.guild_id,
            session_id=self.session_id,
            page_index=self.page_index,
        )

        await interaction.response.send_modal(modal)


async def handle_verify_complete(
    interaction: discord.Interaction,
    answers: list[FormAnswer],
) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "Applications can only be submitted from inside a server.",
            ephemeral=True,
        )
        return

    bot = interaction.client
    application_store = get_application_store(bot)

    if application_store is None:
        await interaction.response.send_message(
            "The application database is not available.",
            ephemeral=True,
        )
        return

    settings_store = getattr(bot, "guild_settings", None)

    if settings_store is None:
        await interaction.response.send_message(
            "Bot settings are not available.",
            ephemeral=True,
        )
        return

    review_channel_id = settings_store.get_review_channel_id(interaction.guild.id)

    if review_channel_id is None:
        await interaction.response.send_message(
            "The review channel has not been configured yet. Staff need to run `/verification review-channel`.",
            ephemeral=True,
        )
        return

    review_channel = bot.get_channel(review_channel_id)

    if review_channel is None:
        try:
            review_channel = await bot.fetch_channel(review_channel_id)
        except discord.HTTPException:
            review_channel = None

    if not isinstance(review_channel, discord.TextChannel):
        await interaction.response.send_message(
            "The configured review channel could not be found. Staff need to run `/verification review-channel` again.",
            ephemeral=True,
        )
        return

    existing_pending_application = await application_store.get_pending_application_for_user(
        guild_id=interaction.guild.id,
        user_id=interaction.user.id,
    )

    if existing_pending_application is not None:
        await interaction.response.send_message(
            "You already have an application waiting for staff review. Please wait for that application to be handled before submitting another one.",
            ephemeral=True,
        )
        return

    automod_terms = settings_store.list_automod_terms(interaction.guild.id)
    automod_match = None

    if settings_store.is_automod_enabled(interaction.guild.id):
        automod_match = find_automod_match(answers, automod_terms)

    application_id = uuid.uuid4().hex

    await application_store.create_application(
        application_id=application_id,
        guild_id=interaction.guild.id,
        user_id=interaction.user.id,
        answers=answers,
    )

    if automod_match is not None:
        application = await application_store.get_application(application_id)

        if application is None:
            await interaction.response.send_message(
                "Something went wrong while creating your application.",
                ephemeral=True,
            )
            return

        automod_reason = "Automatic verification filter match."

        await interaction.response.send_message(
            "Your application could not be submitted for review.",
            ephemeral=True,
        )

        moderator = bot.user or interaction.user
        dm_message = await build_action_dm_message(
            client=bot,
            application=application,
            action="ban",
            moderator=moderator,
            reason=automod_reason,
        )

        dm_sent = await try_dm_user(
            client=bot,
            user_id=interaction.user.id,
            message=dm_message,
        )

        suppression_key = (interaction.guild.id, interaction.user.id)
        departure_suppression = get_departure_suppression_set(bot)
        departure_suppression.add(suppression_key)

        try:
            ban_ok, ban_error = await ban_user_for_automod(
                client=bot,
                guild_id=interaction.guild.id,
                user_id=interaction.user.id,
                reason=automod_reason,
            )
        finally:
            departure_suppression.discard(suppression_key)

        final_reason = automod_reason if ban_ok else f"{automod_reason} Ban failed: {ban_error}"

        await application_store.mark_actioned(
            application_id=application.id,
            status=APPLICATION_STATUS_BANNED if ban_ok else APPLICATION_STATUS_REJECTED,
            moderator_id=moderator.id,
            reason=final_reason,
            dm_sent=dm_sent,
        )

        log_message = await log_application(
            client=bot,
            application=application,
            status="Banned" if ban_ok else "Denied",
            moderator=moderator,
            reason=final_reason,
            dm_sent=dm_sent,
        )

        if log_message is not None:
            await application_store.set_log_message(
                application_id=application.id,
                log_channel_id=log_message.channel.id,
                log_message_id=log_message.id,
            )

        return

    previous_application_links = await application_store.get_previous_application_links(
        guild_id=interaction.guild.id,
        user_id=interaction.user.id,
        exclude_application_id=application_id,
        limit=5,
    )

    invite_text = await get_invite_text_for_user(
        client=bot,
        guild_id=interaction.guild.id,
        user_id=interaction.user.id,
    )

    embeds = build_application_review_embeds(
        application_id=application_id,
        user=interaction.user,
        answers=answers,
        previous_application_links=previous_application_links,
        invite_text=invite_text,
    )

    try:
        review_message = await review_channel.send(
            embeds=embeds,
            view=ApplicationReviewView(application_id),
        )

    except discord.HTTPException:
        await application_store.mark_actioned(
            application_id=application_id,
            status=APPLICATION_STATUS_CANCELLED,
            moderator_id=bot.user.id if bot.user else 0,
            reason="Failed to send review message.",
            dm_sent=None,
        )

        await interaction.response.send_message(
            "Something went wrong while sending your application to staff.",
            ephemeral=True,
        )
        return

    await application_store.set_review_message(
        application_id=application_id,
        review_channel_id=review_channel.id,
        review_message_id=review_message.id,
    )

    await interaction.response.send_message(
        "Your application has been submitted for staff review!\n"
        "Please allow up to 24 hours for your application to be checked.",
        ephemeral=True,
    )


async def perform_moderation_action(
    interaction: discord.Interaction,
    application: StoredApplication,
    action: str,
    reason: str | None,
) -> tuple[bool, str | None]:
    if action == "approve" or action == "deny":
        return True, None

    guild = interaction.client.get_guild(application.guild_id)

    if guild is None:
        return False, "Could not find the server for this application."

    audit_reason = f"Verification {action} by {interaction.user}"

    if reason:
        audit_reason = f"{audit_reason}: {reason}"

    if action == "kick":
        member = guild.get_member(application.user_id)

        if member is None:
            try:
                member = await guild.fetch_member(application.user_id)
            except discord.HTTPException:
                return False, "Could not find that member to kick them."

        try:
            await guild.kick(member, reason=audit_reason)
            return True, None
        except discord.Forbidden:
            return False, "I do not have permission to kick that member."
        except discord.HTTPException:
            return False, "Discord refused the kick request."

    if action == "ban":
        try:
            await guild.ban(
                discord.Object(id=application.user_id),
                reason=audit_reason,
            )
            return True, None
        except discord.Forbidden:
            return False, "I do not have permission to ban that user."
        except discord.HTTPException:
            return False, "Discord refused the ban request."

    return False, f"Unknown action `{action}`."


def action_to_status(action: str) -> tuple[str, str, str]:
    if action == "approve":
        return APPLICATION_STATUS_APPROVED, "Approved", "approved"

    if action == "deny":
        return APPLICATION_STATUS_REJECTED, "Denied", "denied"

    if action == "kick":
        return APPLICATION_STATUS_KICKED, "Kicked", "kicked"

    if action == "ban":
        return APPLICATION_STATUS_BANNED, "Banned", "banned"

    raise ValueError(f"Unknown verification action: {action}")


def get_template_key_for_action(action: str) -> str:
    if action == "approve":
        return DM_TEMPLATE_APPROVED

    if action == "deny":
        return DM_TEMPLATE_DENIED

    if action == "kick":
        return DM_TEMPLATE_KICKED

    if action == "ban":
        return DM_TEMPLATE_BANNED

    return DM_TEMPLATE_DENIED


def build_dm_template_context(
    client: discord.Client,
    application: StoredApplication,
    user: discord.User | discord.Member | None,
    moderator: discord.User | discord.Member | None,
    reason: str | None = None,
) -> dict[str, str]:
    guild = client.get_guild(application.guild_id)
    server_name = guild.name if guild is not None else "the server"

    cleaned_reason = reason.strip() if reason else ""
    reason_block = f"\n\nReason:\n{cleaned_reason}" if cleaned_reason else ""

    return {
        "user": user.mention if user is not None else f"<@{application.user_id}>",
        "user_name": str(user) if user is not None else str(application.user_id),
        "user_id": str(application.user_id),
        "server_name": server_name,
        "moderator": moderator.mention if moderator is not None else "Staff",
        "moderator_name": str(moderator) if moderator is not None else "Staff",
        "moderator_id": str(moderator.id) if moderator is not None else "",
        "application_id": application.id,
        "reason": cleaned_reason,
        "reason_block": reason_block,
    }


async def render_dm_template(
    client: discord.Client,
    application: StoredApplication,
    template_key: str,
    context: dict[str, str],
) -> str:
    template_store = get_dm_template_store(client)

    if template_store is None:
        return render_template_text(
            DEFAULT_DM_TEMPLATES[template_key],
            context,
        )

    template = await template_store.get_template(
        guild_id=application.guild_id,
        template_key=template_key,
    )

    return render_template_text(template.template_text, context)


async def build_action_dm_message(
    client: discord.Client,
    application: StoredApplication,
    action: str,
    moderator: discord.User | discord.Member,
    reason: str | None,
) -> str:
    user = await fetch_user_safely(client, application.user_id)
    template_key = get_template_key_for_action(action)

    context = build_dm_template_context(
        client=client,
        application=application,
        user=user,
        moderator=moderator,
        reason=reason,
    )

    return await render_dm_template(
        client=client,
        application=application,
        template_key=template_key,
        context=context,
    )


async def build_questioning_dm_message(
    client: discord.Client,
    application: StoredApplication,
    user: discord.User | discord.Member | None,
    moderator: discord.User | discord.Member,
) -> str:
    context = build_dm_template_context(
        client=client,
        application=application,
        user=user,
        moderator=moderator,
        reason=None,
    )

    return await render_dm_template(
        client=client,
        application=application,
        template_key=DM_TEMPLATE_QUESTIONING,
        context=context,
    )

def get_departure_suppression_set(
    client: discord.Client,
) -> set[tuple[int, int]]:
    existing = getattr(client, "verification_departure_suppression", None)

    if isinstance(existing, set):
        return existing

    created: set[tuple[int, int]] = set()
    setattr(client, "verification_departure_suppression", created)

    return created


def is_departure_suppressed(
    client: discord.Client,
    guild_id: int,
    user_id: int,
) -> bool:
    return (guild_id, user_id) in get_departure_suppression_set(client)

async def handle_member_left_during_verification(
    client: discord.Client,
    member: discord.Member,
) -> None:
    if is_departure_suppressed(
        client=client,
        guild_id=member.guild.id,
        user_id=member.id,
    ):
        return

    application_store = get_application_store(client)

    if application_store is None:
        return

    application = await application_store.get_pending_application_for_user(
        guild_id=member.guild.id,
        user_id=member.id,
    )

    if application is None:
        return

    moderator = client.user or member

    log_message = await log_application(
        client=client,
        application=application,
        status="Left",
        moderator=moderator,
        reason=None,
        dm_sent=None,
    )

    if log_message is not None:
        await application_store.set_log_message(
            application_id=application.id,
            log_channel_id=log_message.channel.id,
            log_message_id=log_message.id,
        )

    await application_store.mark_actioned(
        application_id=application.id,
        status=APPLICATION_STATUS_LEFT,
        moderator_id=moderator.id,
        reason=None,
        dm_sent=None,
    )

    await delete_review_message(client, application)
    await archive_question_thread(client, application, "Left")

async def complete_application_action(
    interaction: discord.Interaction,
    application: StoredApplication,
    action: str,
    reason: str | None = None,
) -> None:
    application_store = get_application_store(interaction.client)

    if application_store is None:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "The application database is not available.",
                ephemeral=True,
            )
        return

    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=False)

    status, log_status, human_status = action_to_status(action)

    action_dm_message = await build_action_dm_message(
        client=interaction.client,
        application=application,
        action=action,
        moderator=interaction.user,
        reason=reason,
    )

    dm_sent = False
    should_dm_before_action = action in {"kick", "ban"}

    if should_dm_before_action:
        dm_sent = await try_dm_user(
            client=interaction.client,
            user_id=application.user_id,
            message=action_dm_message,
        )

    suppression_key = (application.guild_id, application.user_id)
    should_suppress_departure = action in {"kick", "ban"}
    departure_suppression = get_departure_suppression_set(interaction.client)

    if should_suppress_departure:
        departure_suppression.add(suppression_key)

    try:
        moderation_ok, moderation_error = await perform_moderation_action(
            interaction=interaction,
            application=application,
            action=action,
            reason=reason,
        )

        if not moderation_ok:
            await interaction.followup.send(
                moderation_error or "That moderation action failed.",
                ephemeral=True,
            )
            return

    finally:
        if should_suppress_departure:
            departure_suppression.discard(suppression_key)

    role_failures: list[str] = []

    if action == "approve":
        role_failures = await apply_approval_roles(interaction.client, application)

    if not should_dm_before_action:
        dm_sent = await try_dm_user(
            client=interaction.client,
            user_id=application.user_id,
            message=action_dm_message,
        )

    await application_store.mark_actioned(
        application_id=application.id,
        status=status,
        moderator_id=interaction.user.id,
        reason=reason,
        dm_sent=dm_sent,
    )

    log_message = await log_application(
        client=interaction.client,
        application=application,
        status=log_status,
        moderator=interaction.user,
        reason=reason,
        dm_sent=dm_sent,
    )

    if log_message is not None:
        await application_store.set_log_message(
            application_id=application.id,
            log_channel_id=log_message.channel.id,
            log_message_id=log_message.id,
        )

    await delete_review_message(interaction.client, application)
    await archive_question_thread(interaction.client, application, log_status)

    confirmation_message = f"Application {human_status}."

    if role_failures:
        confirmation_message += "\n" + "\n".join(f"Role warning: {failure}" for failure in role_failures)

    await interaction.followup.send(
        confirmation_message,
        ephemeral=True,
    )

    try:
        if interaction.message is not None:
            await interaction.message.edit(view=None)
    except discord.HTTPException:
        pass



class ActionReasonModal(discord.ui.Modal):
    def __init__(self, application_id: str, action: str) -> None:
        action_title = {
            "deny": "Deny Application",
            "kick": "Kick User",
            "ban": "Ban User",
        }.get(action, "Action Application")

        super().__init__(
            title=action_title,
            custom_id=f"application:action_reason:{action}:{application_id}",
        )

        self.application_id = application_id
        self.action = action

        self.reason = discord.ui.TextInput(
            label="Reason",
            style=discord.TextStyle.paragraph,
            placeholder="Explain the reason for this action.",
            required=True,
            min_length=3,
            max_length=1000,
        )

        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        application_store = get_application_store(interaction.client)

        if application_store is None:
            await interaction.response.send_message(
                "The application database is not available.",
                ephemeral=True,
            )
            return

        application = await application_store.get_application(self.application_id)

        if application is None:
            await interaction.response.send_message(
                "This application no longer exists.",
                ephemeral=True,
            )
            return

        if application.status != APPLICATION_STATUS_PENDING:
            await interaction.response.send_message(
                f"This application is already `{application.status}`.",
                ephemeral=True,
            )
            return

        reason = str(self.reason.value).strip()

        await complete_application_action(
            interaction=interaction,
            application=application,
            action=self.action,
            reason=reason,
        )


class DisabledApplicationReviewView(discord.ui.View):
    def __init__(self, application_id: str) -> None:
        super().__init__(timeout=None)

        self.application_id = application_id

        self.add_item(
            discord.ui.Button(
                label="Approve",
                style=discord.ButtonStyle.success,
                custom_id=f"application_disabled:approve:{application_id}"[:100],
                disabled=True,
            )
        )

        self.add_item(
            discord.ui.Button(
                label="Deny",
                style=discord.ButtonStyle.danger,
                custom_id=f"application_disabled:deny:{application_id}"[:100],
                disabled=True,
            )
        )

        self.add_item(
            discord.ui.Button(
                label="Kick",
                style=discord.ButtonStyle.danger,
                custom_id=f"application_disabled:kick:{application_id}"[:100],
                disabled=True,
            )
        )

        self.add_item(
            discord.ui.Button(
                label="Ban",
                style=discord.ButtonStyle.danger,
                custom_id=f"application_disabled:ban:{application_id}"[:100],
                disabled=True,
            )
        )

        self.add_item(
            discord.ui.Button(
                label="Question",
                style=discord.ButtonStyle.secondary,
                custom_id=f"application_disabled:question:{application_id}"[:100],
                disabled=True,
            )
        )


class ApplicationQuestionControlsView(discord.ui.View):
    def __init__(self, application_id: str) -> None:
        super().__init__(timeout=None)
        self.application_id = application_id

    async def get_pending_application_or_respond(
        self,
        interaction: discord.Interaction,
    ) -> tuple[ApplicationStore, StoredApplication] | None:
        application_store = get_application_store(interaction.client)

        if application_store is None:
            await interaction.response.send_message(
                "The application database is not available.",
                ephemeral=True,
            )
            return None

        application = await application_store.get_application(self.application_id)

        if application is None:
            await interaction.response.send_message(
                "This application no longer exists.",
                ephemeral=True,
            )
            return None

        if application.status != APPLICATION_STATUS_PENDING:
            await interaction.response.send_message(
                f"This application is already `{application.status}`.",
                ephemeral=True,
            )
            return None

        return application_store, application

    @discord.ui.button(
        label="Approve",
        style=discord.ButtonStyle.success,
        custom_id="application_question:approve",
    )
    async def approve_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        result = await self.get_pending_application_or_respond(interaction)

        if result is None:
            return

        _, application = result

        await complete_application_action(
            interaction=interaction,
            application=application,
            action="approve",
        )

    @discord.ui.button(
        label="Deny",
        style=discord.ButtonStyle.danger,
        custom_id="application_question:deny",
    )
    async def deny_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        result = await self.get_pending_application_or_respond(interaction)

        if result is None:
            return

        await interaction.response.send_modal(
            ActionReasonModal(
                application_id=self.application_id,
                action="deny",
            )
        )

    @discord.ui.button(
        label="Kick",
        style=discord.ButtonStyle.danger,
        custom_id="application_question:kick",
    )
    async def kick_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        result = await self.get_pending_application_or_respond(interaction)

        if result is None:
            return

        await interaction.response.send_modal(
            ActionReasonModal(
                application_id=self.application_id,
                action="kick",
            )
        )

    @discord.ui.button(
        label="Ban",
        style=discord.ButtonStyle.danger,
        custom_id="application_question:ban",
    )
    async def ban_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        result = await self.get_pending_application_or_respond(interaction)

        if result is None:
            return

        await interaction.response.send_modal(
            ActionReasonModal(
                application_id=self.application_id,
                action="ban",
            )
        )


class ApplicationReviewView(discord.ui.View):
    def __init__(self, application_id: str) -> None:
        super().__init__(timeout=None)
        self.application_id = application_id

    async def get_pending_application_or_respond(
        self,
        interaction: discord.Interaction,
    ) -> tuple[ApplicationStore, StoredApplication] | None:
        application_store = get_application_store(interaction.client)

        if application_store is None:
            await interaction.response.send_message(
                "The application database is not available.",
                ephemeral=True,
            )
            return None

        application = await application_store.get_application(self.application_id)

        if application is None:
            await interaction.response.send_message(
                "This application no longer exists.",
                ephemeral=True,
            )
            return None

        if application.status != APPLICATION_STATUS_PENDING:
            await interaction.response.send_message(
                f"This application is already `{application.status}`.",
                ephemeral=True,
            )
            return None

        return application_store, application

    @discord.ui.button(
        label="Approve",
        style=discord.ButtonStyle.success,
        custom_id="application:approve",
    )
    async def approve_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        result = await self.get_pending_application_or_respond(interaction)

        if result is None:
            return

        _, application = result

        await complete_application_action(
            interaction=interaction,
            application=application,
            action="approve",
        )

    @discord.ui.button(
        label="Deny",
        style=discord.ButtonStyle.danger,
        custom_id="application:deny",
    )
    async def deny_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        result = await self.get_pending_application_or_respond(interaction)

        if result is None:
            return

        await interaction.response.send_modal(
            ActionReasonModal(
                application_id=self.application_id,
                action="deny",
            )
        )

    @discord.ui.button(
        label="Kick",
        style=discord.ButtonStyle.danger,
        custom_id="application:kick",
    )
    async def kick_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        result = await self.get_pending_application_or_respond(interaction)

        if result is None:
            return

        await interaction.response.send_modal(
            ActionReasonModal(
                application_id=self.application_id,
                action="kick",
            )
        )

    @discord.ui.button(
        label="Ban",
        style=discord.ButtonStyle.danger,
        custom_id="application:ban",
    )
    async def ban_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        result = await self.get_pending_application_or_respond(interaction)

        if result is None:
            return

        await interaction.response.send_modal(
            ActionReasonModal(
                application_id=self.application_id,
                action="ban",
            )
        )

    @discord.ui.button(
        label="Question",
        style=discord.ButtonStyle.primary,
        custom_id="application:question",
    )
    async def question_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        result = await self.get_pending_application_or_respond(interaction)

        if result is None:
            return

        application_store, application = result

        await interaction.response.defer(ephemeral=True, thinking=False)

        existing_thread = await fetch_question_thread(
            interaction.client,
            application.questioning_thread_id,
        )

        if existing_thread is not None:
            await interaction.followup.send(
                f"This application is already being questioned: {existing_thread.mention}",
                ephemeral=True,
            )
            return

        review_message = interaction.message

        if not isinstance(review_message, discord.Message):
            review_message = await fetch_review_message(interaction.client, application)

        if review_message is None:
            await interaction.followup.send(
                "Could not find the original review message to create a thread from.",
                ephemeral=True,
            )
            return

        user = await fetch_user_safely(interaction.client, application.user_id)

        if user is None:
            await interaction.followup.send(
                "Could not fetch the user for this application.",
                ephemeral=True,
            )
            return

        thread_name = f"Question {user.name}"[:100]

        try:
            thread = review_message.thread

            if thread is None:
                thread = await review_message.create_thread(
                    name=thread_name,
                    auto_archive_duration=1440,
                )

        except discord.Forbidden:
            await interaction.followup.send(
                "I do not have permission to create a thread on this message.",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            await interaction.followup.send(
                "Discord refused to create the question thread.",
                ephemeral=True,
            )
            return

        await application_store.set_questioning_thread(
            application_id=application.id,
            questioning_thread_id=thread.id,
        )

        controls_message = await thread.send(
            content=f"{interaction.user.mention}",
            embed=build_question_controls_embed(
                application=application,
                applicant=user,
                opened_by=interaction.user,
            ),
            view=ApplicationQuestionControlsView(application.id),
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False,
            ),
        )

        await application_store.set_question_controls_message(
            application_id=application.id,
            question_controls_message_id=controls_message.id,
        )

        refreshed_application = await application_store.get_application(application.id)

        await update_review_message_with_question_link(
            client=interaction.client,
            application=refreshed_application or application,
            thread=thread,
        )

        question_dm_message = await build_questioning_dm_message(
            client=interaction.client,
            application=application,
            user=user,
            moderator=interaction.user,
        )

        dm_sent = await try_dm_user(
            client=interaction.client,
            user_id=application.user_id,
            message=question_dm_message,
        )


class VerifyView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.primary,
        custom_id="verify:start",
    )
    async def verify_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild is not None:
            application_store = get_application_store(interaction.client)

            if application_store is not None:
                existing_application = await application_store.get_pending_application_for_user(
                    guild_id=interaction.guild.id,
                    user_id=interaction.user.id,
                )

                if existing_application is not None:
                    await interaction.response.send_message(
                        "You already have an application waiting for staff review.",
                        ephemeral=True,
                    )
                    return

        session_id = uuid.uuid4().hex

        VERIFICATION_SESSIONS[session_id] = VerificationSession(
            user_id=interaction.user.id,
            guild_id=interaction.guild.id if interaction.guild else None,
        )

        modal = await build_verify_page_modal(
            client=interaction.client,
            guild_id=interaction.guild.id if interaction.guild else None,
            session_id=session_id,
            page_index=0,
        )

        await interaction.response.send_modal(modal)

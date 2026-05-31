from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import quote_plus
import uuid

import discord

from src.services.application_store import (
    APPLICATION_STATUS_APPROVED,
    APPLICATION_STATUS_CANCELLED,
    APPLICATION_STATUS_PENDING,
    APPLICATION_STATUS_REJECTED,
    ApplicationStore,
    StoredApplication,
)
from src.services.form_loader import FormLoader
from src.utils.form_builder import FormAnswer, build_form_modal


VERIFICATION_FORM_PATH = "data/forms/verification.json"


@dataclass
class VerificationSession:
    user_id: int
    guild_id: int | None
    answers: list[FormAnswer] = field(default_factory=list)


VERIFICATION_SESSIONS: dict[str, VerificationSession] = {}


def get_application_store(client: discord.Client) -> ApplicationStore | None:
    return getattr(client, "application_store", None)


def discord_timestamp(value: datetime, style: str = "R") -> str:
    return f"<t:{int(value.timestamp())}:{style}>"


def trim_embed_value(value: str, limit: int = 1000) -> str:
    cleaned = value.strip()

    if not cleaned:
        return "*No answer provided.*"

    if len(cleaned) <= limit:
        return cleaned

    return cleaned[: limit - 3] + "..."


def get_avatar_reverse_search_url(user: discord.User | discord.Member) -> str:
    avatar_url = user.display_avatar.with_size(1024).url
    return f"https://lens.google.com/uploadbyurl?url={quote_plus(avatar_url)}"


def build_application_review_embeds(
    application_id: str,
    user: discord.User | discord.Member,
    answers: list[FormAnswer],
    previous_application_links: list[str] | None = None,
    questioning_thread_url: str | None = None,
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
            f"**Invite Link:** `Not tracked yet`\n"
            f"[Reverse Image Search Avatar]({reverse_search_url})"
        ),
        inline=False,
    )

    field_count = 1

    if previous_application_links:
        previous_lines = [
            f"[Application {index}]({link})"
            for index, link in enumerate(previous_application_links, start=1)
        ]

        first_embed.add_field(
            name="Previous Application(s):",
            value="\n".join(previous_lines),
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
            name="Being Questioned",
            value=f"[Questioning Link]({questioning_thread_url})",
            inline=False,
        )

    first_embed.set_footer(
        text=f"User ID: {user.id} | Application ID: {application_id}"
    )

    return embeds[:10]


def build_application_log_embeds(
    application_id: str,
    user: discord.User | discord.Member,
    answers: list[FormAnswer],
    status: str,
    moderator: discord.User | discord.Member,
    reason: str | None = None,
    dm_sent: bool | None = None,
) -> list[discord.Embed]:
    embeds: list[discord.Embed] = []

    first_embed = discord.Embed(
        title=f"Verification Application {status}",
        colour=discord.Colour.blurple(),
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

    if reason:
        first_embed.add_field(
            name="Reason",
            value=trim_embed_value(reason),
            inline=False,
        )

    if dm_sent is not None:
        first_embed.add_field(
            name="DM Sent",
            value="Yes" if dm_sent else "No",
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
        await user.send(message)
        return True

    except discord.Forbidden:
        return False

    except discord.HTTPException:
        return False


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

    embeds = build_application_log_embeds(
        application_id=application.id,
        user=user,
        answers=application.answers,
        status=status,
        moderator=moderator,
        reason=reason,
        dm_sent=dm_sent,
    )

    try:
        return await channel.send(embeds=embeds)

    except discord.HTTPException:
        return None


async def delete_review_message(
    client: discord.Client,
    application: StoredApplication,
) -> None:
    if application.review_channel_id is None or application.review_message_id is None:
        return

    channel = client.get_channel(application.review_channel_id)

    if channel is None:
        try:
            channel = await client.fetch_channel(application.review_channel_id)
        except discord.HTTPException:
            return

    if not isinstance(channel, discord.TextChannel):
        return

    try:
        message = channel.get_partial_message(application.review_message_id)
        await message.delete()

    except discord.NotFound:
        pass

    except discord.Forbidden:
        pass

    except discord.HTTPException:
        pass


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

    form = FormLoader.load_form(VERIFICATION_FORM_PATH)
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


def build_verify_page_modal(
    session_id: str,
    page_index: int,
) -> discord.ui.Modal:
    form = FormLoader.load_form(VERIFICATION_FORM_PATH)
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

        modal = build_verify_page_modal(
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
            "The review channel has not been configured yet. Staff need to run `/config channels`.",
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
            "The configured review channel could not be found. Staff need to run `/config channels` again.",
            ephemeral=True,
        )
        return

    application_id = uuid.uuid4().hex

    await application_store.create_application(
        application_id=application_id,
        guild_id=interaction.guild.id,
        user_id=interaction.user.id,
        answers=answers,
    )

    previous_application_links = await application_store.get_previous_application_links(
        guild_id=interaction.guild.id,
        user_id=interaction.user.id,
        exclude_application_id=application_id,
        limit=5,
    )

    embeds = build_application_review_embeds(
        application_id=application_id,
        user=interaction.user,
        answers=answers,
        previous_application_links=previous_application_links,
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


class RejectReasonModal(discord.ui.Modal):
    def __init__(self, application_id: str) -> None:
        super().__init__(
            title="Reject Application",
            custom_id=f"application:reject_reason:{application_id}",
        )

        self.application_id = application_id

        self.reason = discord.ui.TextInput(
            label="Rejection reason",
            style=discord.TextStyle.paragraph,
            placeholder="Explain why the application was rejected.",
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

        dm_sent = await try_dm_user(
            client=interaction.client,
            user_id=application.user_id,
            message=(
                "Your verification application has been rejected.\n\n"
                f"Reason: {reason}"
            ),
        )

        await application_store.mark_actioned(
            application_id=application.id,
            status=APPLICATION_STATUS_REJECTED,
            moderator_id=interaction.user.id,
            reason=reason,
            dm_sent=dm_sent,
        )

        log_message = await log_application(
            client=interaction.client,
            application=application,
            status="Rejected",
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

        await interaction.response.send_message(
            f"Application rejected. DM sent: `{dm_sent}`",
            ephemeral=True,
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

        application_store, application = result

        await interaction.response.defer(ephemeral=True, thinking=False)

        dm_sent = await try_dm_user(
            client=interaction.client,
            user_id=application.user_id,
            message="Your verification application has been approved.",
        )

        await application_store.mark_actioned(
            application_id=application.id,
            status=APPLICATION_STATUS_APPROVED,
            moderator_id=interaction.user.id,
            reason=None,
            dm_sent=dm_sent,
        )

        log_message = await log_application(
            client=interaction.client,
            application=application,
            status="Approved",
            moderator=interaction.user,
            dm_sent=dm_sent,
        )

        if log_message is not None:
            await application_store.set_log_message(
                application_id=application.id,
                log_channel_id=log_message.channel.id,
                log_message_id=log_message.id,
            )

        await delete_review_message(interaction.client, application)

    @discord.ui.button(
        label="Reject",
        style=discord.ButtonStyle.danger,
        custom_id="application:reject",
    )
    async def reject_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        result = await self.get_pending_application_or_respond(interaction)

        if result is None:
            return

        modal = RejectReasonModal(self.application_id)

        await interaction.response.send_modal(modal)


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
        session_id = uuid.uuid4().hex

        VERIFICATION_SESSIONS[session_id] = VerificationSession(
            user_id=interaction.user.id,
            guild_id=interaction.guild.id if interaction.guild else None,
        )

        modal = build_verify_page_modal(
            session_id=session_id,
            page_index=0,
        )

        await interaction.response.send_modal(modal)
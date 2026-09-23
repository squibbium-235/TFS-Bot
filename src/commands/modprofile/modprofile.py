from __future__ import annotations

import re

from datetime import (
    datetime,
    timezone,
)

import discord

from discord import app_commands
from discord.ext import commands

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

from src.services.guild_settings import (
    GuildSettingsStore,
)

from src.services.moderation_store import (
    ModerationCase,
    ModerationStore,
    UserModProfile,
)


USER_ID_PATTERN = re.compile(
    r"^(?:<@!?)?(\d+)>?$"
)


VERIFICATION_STATUS_DISPLAY = {
    APPLICATION_STATUS_PENDING: (
        "🟡",
        "Pending",
    ),
    APPLICATION_STATUS_APPROVED: (
        "✅",
        "Approved",
    ),
    APPLICATION_STATUS_REJECTED: (
        "❌",
        "Rejected",
    ),
    APPLICATION_STATUS_KICKED: (
        "🥾",
        "Kicked",
    ),
    APPLICATION_STATUS_BANNED: (
        "⛔",
        "Banned",
    ),
    APPLICATION_STATUS_LEFT: (
        "🚪",
        "Left",
    ),
    APPLICATION_STATUS_CANCELLED: (
        "⚪",
        "Cancelled",
    ),
}


def get_moderation_store(
    bot: commands.Bot,
) -> ModerationStore | None:
    return getattr(
        bot,
        "moderation_store",
        None,
    )


def get_application_store(
    bot: commands.Bot,
) -> ApplicationStore | None:
    return getattr(
        bot,
        "application_store",
        None,
    )


def get_guild_settings(
    bot: commands.Bot,
) -> GuildSettingsStore | None:
    return getattr(
        bot,
        "guild_settings",
        None,
    )


async def resolve_profile_user(
    bot: commands.Bot,
    guild: discord.Guild,
    value: str,
) -> tuple[
    discord.User | discord.Member | None,
    str | None,
]:
    value = value.strip()

    id_match = USER_ID_PATTERN.fullmatch(
        value
    )

    if id_match is not None:
        user_id = int(
            id_match.group(1)
        )

        member = guild.get_member(
            user_id
        )

        if member is not None:
            return member, None

        cached_user = bot.get_user(
            user_id
        )

        if cached_user is not None:
            return cached_user, None

        try:
            user = await bot.fetch_user(
                user_id
            )

        except discord.NotFound:
            return (
                None,
                (
                    "I could not find a Discord "
                    "user with that ID."
                ),
            )

        except discord.HTTPException:
            return (
                None,
                (
                    "Discord could not resolve "
                    "that user right now."
                ),
            )

        return user, None

    search_value = value.casefold()

    matches: list[
        discord.Member
    ] = []

    for member in guild.members:
        possible_names = {
            member.name.casefold(),
            member.display_name.casefold(),
        }

        if member.global_name:
            possible_names.add(
                member.global_name.casefold()
            )

        if search_value in possible_names:
            matches.append(
                member
            )

    if len(matches) == 1:
        return matches[0], None

    if len(matches) > 1:
        return (
            None,
            (
                "More than one member matches "
                f"`{value}`. Use their user ID "
                "or mention instead."
            ),
        )

    return (
        None,
        (
            f"I could not find `{value}` in "
            "this server. If they have left the "
            "server, use their Discord user ID."
        ),
    )


def build_thread_url(
    guild_id: int,
    thread_id: int,
) -> str:
    return (
        "https://discord.com/channels/"
        f"{guild_id}/{thread_id}"
    )


def format_short_date(
    raw_date: str,
) -> str:
    try:
        parsed = datetime.fromisoformat(
            raw_date
        )

    except ValueError:
        return "Unknown"

    return parsed.strftime(
        "%d/%m/%y"
    )


def format_verification_attempt(
    application: StoredApplication,
) -> str:
    emoji, status = (
        VERIFICATION_STATUS_DISPLAY.get(
            application.status,
            (
                "•",
                application.status.title(),
            ),
        )
    )

    date_text = format_short_date(
        application.submitted_at
    )

    parts = [
        f"{emoji} **{date_text}**",
        status,
    ]

    if application.moderator_id:
        parts.append(
            f"<@{application.moderator_id}>"
        )

    message_url = (
        application.best_message_url
    )

    if message_url:
        parts.append(
            f"[View]({message_url})"
        )

    return " • ".join(
        parts
    )


def split_embed_lines(
    lines: list[str],
    *,
    maximum_length: int = 1000,
) -> list[str]:
    if not lines:
        return []

    chunks: list[str] = []
    current_lines: list[str] = []
    current_length = 0

    for line in lines:
        extra_length = (
            len(line)
            + (
                1
                if current_lines
                else 0
            )
        )

        if (
            current_lines
            and (
                current_length
                + extra_length
                > maximum_length
            )
        ):
            chunks.append(
                "\n".join(
                    current_lines
                )
            )

            current_lines = []
            current_length = 0

        current_lines.append(
            line
        )

        current_length += (
            len(line)
            + (
                1
                if len(current_lines) > 1
                else 0
            )
        )

    if current_lines:
        chunks.append(
            "\n".join(
                current_lines
            )
        )

    return chunks


def format_case(
    moderation_case: ModerationCase,
) -> str:
    action = (
        moderation_case.action
        .replace("_", " ")
        .title()
    )

    date_text = format_short_date(
        moderation_case.created_at
    )

    line = (
        f"**#{moderation_case.case_number}** "
        f"• {date_text} • "
        f"**{action}**"
    )

    if moderation_case.moderator_id:
        line += (
            f" • <@"
            f"{moderation_case.moderator_id}"
            f">"
        )

    if moderation_case.reason:
        reason = (
            moderation_case.reason
            .replace(
                "\n",
                " ",
            )
            .strip()
        )

        if len(reason) > 100:
            reason = (
                reason[:97]
                + "..."
            )

        line += (
            f"\n↳ {reason}"
        )

    return line


def audit_action_name(
    entry: discord.AuditLogEntry,
) -> str | None:
    if (
        entry.action
        == discord.AuditLogAction.ban
    ):
        return "Ban"

    if (
        entry.action
        == discord.AuditLogAction.unban
    ):
        return "Unban"

    if (
        entry.action
        == discord.AuditLogAction.kick
    ):
        return "Kick"

    if (
        entry.action
        == discord.AuditLogAction.member_update
    ):
        before_timeout = getattr(
            entry.before,
            "timed_out_until",
            None,
        )

        after_timeout = getattr(
            entry.after,
            "timed_out_until",
            None,
        )

        if (
            before_timeout
            != after_timeout
        ):
            if after_timeout is None:
                return "Timeout Removed"

            return "Timeout"

    if (
        entry.action
        == discord.AuditLogAction.member_role_update
    ):
        return "Role Update"

    return None


async def get_recent_audit_history(
    guild: discord.Guild,
    *,
    user_id: int,
) -> tuple[
    list[str],
    bool,
]:
    lines: list[str] = []

    try:
        async for entry in guild.audit_logs(
            limit=250,
        ):
            target = entry.target

            if target is None:
                continue

            target_id = getattr(
                target,
                "id",
                None,
            )

            if target_id != user_id:
                continue

            action_name = (
                audit_action_name(
                    entry
                )
            )

            if action_name is None:
                continue

            date_text = (
                entry.created_at.strftime(
                    "%d/%m/%y"
                )
            )

            executor = entry.user

            if executor is not None:
                executor_text = (
                    f"<@{executor.id}>"
                )

            else:
                executor_text = "Unknown"

            line = (
                f"**{date_text}** • "
                f"**{action_name}** • "
                f"{executor_text}"
            )

            if entry.reason:
                reason = (
                    entry.reason
                    .replace(
                        "\n",
                        " ",
                    )
                    .strip()
                )

                if len(reason) > 100:
                    reason = (
                        reason[:97]
                        + "..."
                    )

                line += (
                    f"\n↳ {reason}"
                )

            lines.append(
                line
            )

    except discord.Forbidden:
        return [], False

    except discord.HTTPException:
        return [], False

    return lines, True


def build_profile_embed(
    user: discord.User | discord.Member,
    *,
    applications: list[
        StoredApplication
    ],
    moderation_cases: list[
        ModerationCase
    ],
    audit_history: list[str],
    audit_available: bool,
    thread_url: str | None,
) -> discord.Embed:
    embed = discord.Embed(
        title="User Moderation Profile",
        colour=discord.Colour.blurple(),
        timestamp=discord.utils.utcnow(),
    )

    embed.set_author(
        name=str(user),
        icon_url=(
            user.display_avatar.url
        ),
    )

    embed.set_thumbnail(
        url=user.display_avatar.url
    )

    embed.add_field(
        name="👤 User",
        value=(
            f"{user.mention}\n"
            f"`{user.id}`"
        ),
        inline=False,
    )

    embed.add_field(
        name="Account Created",
        value=discord.utils.format_dt(
            user.created_at,
            style="F",
        ),
        inline=True,
    )

    if (
        isinstance(
            user,
            discord.Member,
        )
        and user.joined_at is not None
    ):
        joined_text = (
            discord.utils.format_dt(
                user.joined_at,
                style="F",
            )
        )

    elif isinstance(
        user,
        discord.Member,
    ):
        joined_text = "Unknown"

    else:
        joined_text = (
            "Not currently in server"
        )

    embed.add_field(
        name="Joined Server",
        value=joined_text,
        inline=True,
    )

    verification_lines = [
        format_verification_attempt(
            application
        )
        for application in applications
    ]

    if verification_lines:
        chunks = split_embed_lines(
            verification_lines
        )

        for index, chunk in enumerate(
            chunks
        ):
            if index == 0:
                field_name = (
                    "✅ Verification Attempts"
                )

            else:
                field_name = (
                    "✅ Verification Attempts "
                    "(continued)"
                )

            embed.add_field(
                name=field_name,
                value=chunk,
                inline=False,
            )

    else:
        embed.add_field(
            name="✅ Verification Attempts",
            value=(
                "No verification attempts "
                "recorded."
            ),
            inline=False,
        )

    case_lines = [
        format_case(
            moderation_case
        )
        for moderation_case
        in moderation_cases
    ]

    if case_lines:
        for index, chunk in enumerate(
            split_embed_lines(
                case_lines
            )
        ):
            embed.add_field(
                name=(
                    "🛡️ TFSBot Moderation Cases"
                    if index == 0
                    else (
                        "🛡️ TFSBot Cases "
                        "(continued)"
                    )
                ),
                value=chunk,
                inline=False,
            )

    audit_field_lines = audit_history

    if audit_field_lines:
        for index, chunk in enumerate(
            split_embed_lines(
                audit_field_lines
            )
        ):
            embed.add_field(
                name=(
                    "📋 Discord Moderation Log"
                    if index == 0
                    else (
                        "📋 Discord Moderation Log "
                        "(continued)"
                    )
                ),
                value=chunk,
                inline=False,
            )

    elif audit_available:
        embed.add_field(
            name="📋 Discord Moderation Log",
            value=(
                "No recent moderation actions "
                "found in the Discord audit log."
            ),
            inline=False,
        )

    else:
        embed.add_field(
            name="📋 Discord Moderation Log",
            value=(
                "Audit log unavailable. "
                "TFSBot needs the "
                "`View Audit Log` permission."
            ),
            inline=False,
        )

    if thread_url is not None:
        notes_value = (
            "[Open staff notes & discussion]"
            f"({thread_url})"
        )

    else:
        notes_value = (
            "Creating notes thread..."
        )

    embed.add_field(
        name="💬 Staff Notes",
        value=notes_value,
        inline=False,
    )

    embed.set_footer(
        text=(
            f"{len(applications)} verification "
            f"attempt(s) • "
            f"{len(moderation_cases)} TFSBot "
            f"case(s)"
        )
    )

    return embed


class ModProfileCommands(
    commands.Cog
):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

    @app_commands.command(
        name="modprofile",
        description=(
            "Open or create a user's "
            "moderation profile."
        ),
    )
    @app_commands.describe(
        user=(
            "User ID, username, "
            "display name, or mention."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        moderate_members=True
    )
    async def modprofile(
        self,
        interaction: discord.Interaction,
        user: str,
    ) -> None:
        assert interaction.guild is not None

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        resolved_user, error = (
            await resolve_profile_user(
                self.bot,
                interaction.guild,
                user,
            )
        )

        if resolved_user is None:
            await interaction.followup.send(
                error
                or (
                    "That user could not "
                    "be found."
                ),
                ephemeral=True,
            )
            return

        moderation_store = (
            get_moderation_store(
                self.bot
            )
        )

        application_store = (
            get_application_store(
                self.bot
            )
        )

        guild_settings = (
            get_guild_settings(
                self.bot
            )
        )

        if (
            moderation_store is None
            or application_store is None
            or guild_settings is None
        ):
            await interaction.followup.send(
                (
                    "The moderation profile "
                    "system is not available."
                ),
                ephemeral=True,
            )
            return

        guild = interaction.guild
        guild_id = guild.id
        user_id = resolved_user.id

        applications = (
            await application_store
            .list_applications_for_user(
                guild_id=guild_id,
                user_id=user_id,
            )
        )

        moderation_cases = (
            await moderation_store
            .list_cases_for_user(
                guild_id=guild_id,
                user_id=user_id,
                limit=100,
            )
        )

        (
            audit_history,
            audit_available,
        ) = await get_recent_audit_history(
            guild,
            user_id=user_id,
        )

        existing_profile = (
            await moderation_store.get_profile(
                guild_id=guild_id,
                user_id=user_id,
            )
        )

        if existing_profile is not None:
            thread = (
                await self._get_profile_thread(
                    existing_profile
                )
            )

            if thread is not None:
                thread_url = build_thread_url(
                    guild_id,
                    thread.id,
                )

                embed = build_profile_embed(
                    resolved_user,
                    applications=applications,
                    moderation_cases=(
                        moderation_cases
                    ),
                    audit_history=(
                        audit_history
                    ),
                    audit_available=(
                        audit_available
                    ),
                    thread_url=thread_url,
                )

                refreshed = (
                    await self
                    ._refresh_profile_message(
                        existing_profile,
                        embed,
                    )
                )

                if thread.archived:
                    try:
                        await thread.edit(
                            archived=False,
                            reason=(
                                "Moderation "
                                "profile opened."
                            ),
                        )

                    except discord.HTTPException:
                        pass

                if not refreshed:
                    await moderation_store.delete_profile(
                        guild_id=guild_id,
                        user_id=user_id,
                    )

                else:
                    await interaction.followup.send(
                        embed=embed,
                        ephemeral=True,
                    )

                    return

        log_channel_id = (
            guild_settings
            .get_moderation_log_channel_id(
                guild_id
            )
        )

        if log_channel_id is None:
            await interaction.followup.send(
                (
                    "No moderation log channel "
                    "has been configured."
                ),
                ephemeral=True,
            )
            return

        log_channel = guild.get_channel(
            log_channel_id
        )

        if log_channel is None:
            try:
                fetched_channel = (
                    await self.bot.fetch_channel(
                        log_channel_id
                    )
                )

            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException,
            ):
                fetched_channel = None

            if isinstance(
                fetched_channel,
                discord.TextChannel,
            ):
                log_channel = (
                    fetched_channel
                )

        if not isinstance(
            log_channel,
            discord.TextChannel,
        ):
            await interaction.followup.send(
                (
                    "The configured moderation "
                    "log channel is missing or "
                    "is not a text channel."
                ),
                ephemeral=True,
            )
            return

        preliminary_embed = (
            build_profile_embed(
                resolved_user,
                applications=applications,
                moderation_cases=(
                    moderation_cases
                ),
                audit_history=(
                    audit_history
                ),
                audit_available=(
                    audit_available
                ),
                thread_url=None,
            )
        )

        try:
            profile_message = (
                await log_channel.send(
                    embed=preliminary_embed
                )
            )

            thread_name = (
                f"{resolved_user.name} "
                f"• {resolved_user.id}"
            )[:100]

            thread = (
                await profile_message
                .create_thread(
                    name=thread_name,
                    reason=(
                        "TFSBot moderation "
                        "profile created."
                    ),
                )
            )

        except discord.Forbidden:
            await interaction.followup.send(
                (
                    "I do not have permission "
                    "to create the moderation "
                    "profile or notes thread."
                ),
                ephemeral=True,
            )
            return

        except discord.HTTPException as error:
            await interaction.followup.send(
                (
                    "Discord rejected the "
                    "moderation profile "
                    "creation:\n"
                    f"`{error}`"
                ),
                ephemeral=True,
            )
            return

        try:
            profile = (
                await moderation_store
                .save_profile(
                    guild_id=guild_id,
                    user_id=user_id,
                    channel_id=(
                        log_channel.id
                    ),
                    message_id=(
                        profile_message.id
                    ),
                    thread_id=thread.id,
                )
            )

        except Exception:
            try:
                await thread.delete()

            except discord.HTTPException:
                pass

            try:
                await profile_message.delete()

            except discord.HTTPException:
                pass

            raise

        thread_url = build_thread_url(
            guild_id,
            thread.id,
        )

        final_embed = build_profile_embed(
            resolved_user,
            applications=applications,
            moderation_cases=(
                moderation_cases
            ),
            audit_history=(
                audit_history
            ),
            audit_available=(
                audit_available
            ),
            thread_url=thread_url,
        )

        try:
            await profile_message.edit(
                embed=final_embed
            )

        except discord.HTTPException:
            pass

        try:
            await thread.send(
                (
                    "### Staff Notes\n"
                    f"Moderation profile for "
                    f"{resolved_user.mention}\n"
                    f"User ID: `{user_id}`\n\n"
                    "Use this thread for staff "
                    "notes, context, and "
                    "discussion about this user."
                ),
                allowed_mentions=(
                    discord.AllowedMentions.none()
                ),
            )

        except discord.HTTPException:
            pass

        await interaction.followup.send(
            embed=final_embed,
            ephemeral=True,
        )

    async def _get_profile_thread(
        self,
        profile: UserModProfile,
    ) -> discord.Thread | None:
        channel = self.bot.get_channel(
            profile.thread_id
        )

        if isinstance(
            channel,
            discord.Thread,
        ):
            return channel

        try:
            fetched = (
                await self.bot.fetch_channel(
                    profile.thread_id
                )
            )

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException,
        ):
            return None

        if isinstance(
            fetched,
            discord.Thread,
        ):
            return fetched

        return None

    async def _refresh_profile_message(
        self,
        profile: UserModProfile,
        embed: discord.Embed,
    ) -> bool:
        channel = self.bot.get_channel(
            profile.channel_id
        )

        if channel is None:
            try:
                channel = (
                    await self.bot.fetch_channel(
                        profile.channel_id
                    )
                )

            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException,
            ):
                return False

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            return False

        try:
            message = (
                await channel.fetch_message(
                    profile.message_id
                )
            )

            await message.edit(
                embed=embed
            )

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException,
        ):
            return False

        return True


async def setup(
    bot: commands.Bot,
) -> None:
    await bot.add_cog(
        ModProfileCommands(
            bot
        )
    )
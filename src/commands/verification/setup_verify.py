from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from src.commands.verification.verification import (
    VerifyView,
    cancel_all_pending_applications_for_guild,
    cancel_pending_application_by_user_id,
)
from src.services.forms.constants import (
    FORM_KEY_VERIFICATION,
    VERIFICATION_FORM_PATH,
)
from src.services.forms.form_store import FormStore


def get_form_store(bot: commands.Bot) -> FormStore:
    form_store = getattr(bot, "form_store", None)

    if form_store is None:
        raise RuntimeError("Form store is not available.")

    return form_store


async def form_key_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if interaction.guild is None:
        return []

    form_store = getattr(
        interaction.client,
        "form_store",
        None,
    )

    if form_store is None:
        return []

    forms = await form_store.list_forms(
        interaction.guild.id
    )

    current = current.lower().strip()

    choices: list[app_commands.Choice[str]] = []

    for form in forms:
        if current and current not in form.form_key.lower():
            continue

        choices.append(
            app_commands.Choice(
                name=f"{form.form_key} - {form.title}",
                value=form.form_key,
            )
        )

    return choices[:25]


def build_verify_embed(
    guild: discord.Guild,
    form_title: str,
    image_url: str | None = None,
    thumbnail_url: str | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{guild.name} Verification",
        description=(
            "Welcome!\n\n"
            f"Please complete the "
            f"**{discord.utils.escape_markdown(form_title)}** "
            "form to apply for access to the server.\n\n"
            "Click the button below to begin."
        ),
        colour=discord.Colour.blurple(),
    )

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    elif guild.icon is not None:
        embed.set_thumbnail(url=guild.icon.url)

    if image_url:
        embed.set_image(url=image_url)

    embed.set_footer(
        text="TFSBot Verification"
    )

    return embed


def make_attachment_filename(
    prefix: str,
    attachment: discord.Attachment,
) -> str:
    filename = (
        attachment.filename
        or f"{prefix}.png"
    )

    filename = (
        filename
        .replace("/", "_")
        .replace("\\", "_")
    )

    return f"{prefix}_{filename}"


async def build_panel_attachment_files(
    image: discord.Attachment | None,
    thumbnail: discord.Attachment | None,
) -> tuple[
    str | None,
    str | None,
    list[discord.File],
]:
    files: list[discord.File] = []

    image_url: str | None = None
    thumbnail_url: str | None = None

    for attachment, prefix in (
        (image, "panel_image"),
        (thumbnail, "panel_thumbnail"),
    ):
        if attachment is None:
            continue

        if (
            attachment.content_type
            and not attachment.content_type.startswith("image/")
        ):
            raise RuntimeError(
                f"{attachment.filename} "
                "is not an image attachment."
            )

        filename = make_attachment_filename(
            prefix,
            attachment,
        )

        file = await attachment.to_file(
            filename=filename
        )

        files.append(file)

        attachment_url = (
            f"attachment://{filename}"
        )

        if prefix == "panel_image":
            image_url = attachment_url
        else:
            thumbnail_url = attachment_url

    return (
        image_url,
        thumbnail_url,
        files,
    )


def close_discord_files(
    files: list[discord.File],
) -> None:
    for file in files:
        try:
            file.close()

        except Exception:
            pass


def format_channel(
    guild: discord.Guild,
    channel_id: int | None,
) -> str:
    if channel_id is None:
        return "`Not configured`"

    channel = guild.get_channel(
        channel_id
    )

    if channel is None:
        return (
            "`Missing channel` "
            f"(`{channel_id}`)"
        )

    return channel.mention


def format_role(
    guild: discord.Guild,
    role_id: int | None,
) -> str:
    if role_id is None:
        return "`Not configured`"

    role = guild.get_role(
        role_id
    )

    if role is None:
        return (
            "`Missing role` "
            f"(`{role_id}`)"
        )

    return role.mention


def build_verification_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Verification Help",
        description=(
            "Commands for configuring and managing "
            "the server verification system.\n\n"
            "All administration responses are private "
            "to you unless the command explicitly posts "
            "something into a channel."
        ),
        colour=discord.Colour.blurple(),
    )

    embed.add_field(
        name="Overview",
        value=(
            "`/verification help`\n"
            "Shows this help page.\n\n"
            "`/verification status`\n"
            "Shows the current verification configuration, "
            "including channels, roles, automod, invite "
            "tracking and welcome messages."
        ),
        inline=False,
    )

    embed.add_field(
        name="Verification Panel",
        value=(
            "`/verification panel`\n"
            "Posts the public verification panel into a "
            "channel. You can choose the form and optionally "
            "attach a large image or thumbnail."
        ),
        inline=False,
    )

    embed.add_field(
        name="Channels",
        value=(
            "`/verification review-channel`\n"
            "Sets where submitted verification applications "
            "are sent for staff review.\n\n"
            "`/verification log-channel`\n"
            "Sets where verification application logs "
            "are posted."
        ),
        inline=False,
    )

    embed.add_field(
        name="Approval Roles",
        value=(
            "`/verification approved-add-role`\n"
            "Sets the role given to someone when their "
            "verification is approved.\n\n"
            "`/verification approved-remove-role`\n"
            "Sets the role removed when somebody is approved, "
            "such as an Unverified role.\n\n"
            "`/verification clear-approved-add-role`\n"
            "Clears the configured role to give.\n\n"
            "`/verification clear-approved-remove-role`\n"
            "Clears the configured role to remove."
        ),
        inline=False,
    )

    embed.add_field(
        name="Application Automod",
        value=(
            "`/verification automod-enabled`\n"
            "Enables or disables verification application "
            "automod.\n\n"
            "`/verification automod-add`\n"
            "Adds a blocked term.\n\n"
            "`/verification automod-remove`\n"
            "Removes a blocked term.\n\n"
            "`/verification automod-list`\n"
            "Shows the current automod status and blocked terms."
        ),
        inline=False,
    )

    embed.add_field(
        name="Application Management",
        value=(
            "`/verification cancel-user`\n"
            "Cancels and resets one user's pending "
            "verification application. Requires `CANCEL` "
            "as confirmation.\n\n"
            "`/verification cancel-all`\n"
            "Cancels and resets every pending verification "
            "application in the server. Also requires "
            "`CANCEL` as confirmation."
        ),
        inline=False,
    )

    embed.add_field(
        name="Related Commands",
        value=(
            "`/welcome ...`\n"
            "Configures the welcome message sent after a "
            "verification application is approved.\n\n"
            "`/permissions ...`\n"
            "Controls which bot permission levels can use "
            "commands."
        ),
        inline=False,
    )

    embed.set_footer(
        text=(
            "TFSBot Verification • "
            "Configuration commands respond ephemerally"
        )
    )

    return embed


class VerificationConfigCommand(
    commands.Cog
):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

    verification_group = app_commands.Group(
        name="verification",
        description="Configure verification settings.",
    )

    @verification_group.command(
        name="help",
        description=(
            "Explain the verification commands."
        ),
    )
    @app_commands.guild_only()
    async def verification_help(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.send_message(
            embed=build_verification_help_embed(),
            ephemeral=True,
        )

    @verification_group.command(
        name="status",
        description=(
            "Show the current verification configuration."
        ),
    )
    @app_commands.guild_only()
    async def verification_status(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        guild = interaction.guild
        guild_id = guild.id

        settings_store = getattr(
            self.bot,
            "guild_settings",
            None,
        )

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        form_key = (
            settings_store
            .get_verification_form_key(
                guild_id
            )
            or FORM_KEY_VERIFICATION
        )

        review_channel_id = (
            settings_store
            .get_review_channel_id(
                guild_id
            )
        )

        log_channel_id = (
            settings_store
            .get_application_log_channel_id(
                guild_id
            )
        )

        add_role_id = (
            settings_store
            .get_approved_add_role_id(
                guild_id
            )
        )

        remove_role_id = (
            settings_store
            .get_approved_remove_role_id(
                guild_id
            )
        )

        automod_enabled = (
            settings_store
            .is_automod_enabled(
                guild_id
            )
        )

        automod_terms = (
            settings_store
            .list_automod_terms(
                guild_id
            )
        )

        invite_tracking_ready = bool(
            getattr(
                self.bot,
                "invite_tracker_ready",
                False,
            )
        )

        welcome_enabled = False
        welcome_channel_id: int | None = None
        welcome_available = False

        welcome_store = getattr(
            self.bot,
            "welcome_store",
            None,
        )

        if welcome_store is not None:
            try:
                welcome_settings = (
                    await welcome_store
                    .get_settings(
                        guild_id
                    )
                )

                welcome_enabled = (
                    welcome_settings.enabled
                )

                welcome_channel_id = (
                    welcome_settings.channel_id
                )

                welcome_available = True

            except Exception:
                welcome_available = False

        embed = discord.Embed(
            title="Verification Configuration",
            description=(
                "Current verification settings for "
                f"**{discord.utils.escape_markdown(guild.name)}**."
            ),
            colour=discord.Colour.blurple(),
        )

        embed.add_field(
            name="Form",
            value=f"`{form_key}`",
            inline=True,
        )

        embed.add_field(
            name="Review Channel",
            value=format_channel(
                guild,
                review_channel_id,
            ),
            inline=True,
        )

        embed.add_field(
            name="Log Channel",
            value=format_channel(
                guild,
                log_channel_id,
            ),
            inline=True,
        )

        embed.add_field(
            name="Approval Roles",
            value=(
                "**Give:** "
                f"{format_role(guild, add_role_id)}\n"
                "**Remove:** "
                f"{format_role(guild, remove_role_id)}"
            ),
            inline=False,
        )

        embed.add_field(
            name="Automod",
            value=(
                "**Status:** "
                f"{'Enabled' if automod_enabled else 'Disabled'}\n"
                "**Blocked terms:** "
                f"{len(automod_terms)}"
            ),
            inline=True,
        )

        embed.add_field(
            name="Invite Tracking",
            value=(
                "Ready"
                if invite_tracking_ready
                else "Not ready"
            ),
            inline=True,
        )

        if welcome_available:
            welcome_text = (
                "**Status:** "
                f"{'Enabled' if welcome_enabled else 'Disabled'}\n"
                "**Channel:** "
                f"{format_channel(guild, welcome_channel_id)}"
            )
        else:
            welcome_text = "`Unavailable`"

        embed.add_field(
            name="Welcome Message",
            value=welcome_text,
            inline=True,
        )

        embed.set_footer(
            text=(
                "Use /verification help for command information."
            )
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @verification_group.command(
        name="panel",
        description=(
            "Post the verification panel using a selected form."
        ),
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(
        form=form_key_autocomplete
    )
    async def verification_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        form: str = FORM_KEY_VERIFICATION,
        image: discord.Attachment | None = None,
        thumbnail: discord.Attachment | None = None,
    ) -> None:
        assert interaction.guild is not None

        form_key = form.lower().strip()

        form_store = get_form_store(
            self.bot
        )

        try:
            form_config = (
                await form_store.get_form_config(
                    guild_id=interaction.guild.id,
                    form_key=form_key,
                    fallback_json_path=(
                        VERIFICATION_FORM_PATH
                    ),
                )
            )

        except Exception as error:
            await interaction.response.send_message(
                (
                    f"Could not load form "
                    f"`{form_key}`: `{error}`"
                ),
                ephemeral=True,
            )
            return

        settings_store = getattr(
            self.bot,
            "guild_settings",
            None,
        )

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        settings_store.set_verification_form_key(
            guild_id=interaction.guild.id,
            form_key=form_key,
        )

        try:
            (
                image_url,
                thumbnail_url,
                files,
            ) = await build_panel_attachment_files(
                image=image,
                thumbnail=thumbnail,
            )

            await channel.send(
                embed=build_verify_embed(
                    guild=interaction.guild,
                    form_title=form_config.title,
                    image_url=image_url,
                    thumbnail_url=thumbnail_url,
                ),
                view=VerifyView(),
                files=files if files else None,
            )

        except Exception as error:
            await interaction.response.send_message(
                (
                    "Could not post verification "
                    f"panel: `{error}`"
                ),
                ephemeral=True,
            )
            return

        finally:
            close_discord_files(
                files
                if "files" in locals()
                else []
            )

        await interaction.response.send_message(
            (
                "Verification panel posted in "
                f"{channel.mention} using form "
                f"`{form_key}`."
            ),
            ephemeral=True,
        )

    @verification_group.command(
        name="review-channel",
        description=(
            "Set the channel where verification "
            "applications are reviewed."
        ),
    )
    @app_commands.guild_only()
    async def verification_review_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(
            self.bot,
            "guild_settings",
            None,
        )

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        settings_store.set_review_channel_id(
            interaction.guild.id,
            channel.id,
        )

        await interaction.response.send_message(
            (
                "Verification review channel set to "
                f"{channel.mention}."
            ),
            ephemeral=True,
        )

    @verification_group.command(
        name="log-channel",
        description=(
            "Set the channel where verification "
            "application logs are posted."
        ),
    )
    @app_commands.guild_only()
    async def verification_log_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(
            self.bot,
            "guild_settings",
            None,
        )

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        settings_store.set_application_log_channel_id(
            interaction.guild.id,
            channel.id,
        )

        await interaction.response.send_message(
            (
                "Verification log channel set to "
                f"{channel.mention}."
            ),
            ephemeral=True,
        )

    @verification_group.command(
        name="approved-add-role",
        description=(
            "Set the role given to users when their "
            "verification is approved."
        ),
    )
    @app_commands.guild_only()
    async def verification_approved_add_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(
            self.bot,
            "guild_settings",
            None,
        )

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        settings_store.set_approved_add_role_id(
            interaction.guild.id,
            role.id,
        )

        await interaction.response.send_message(
            (
                "Approved users will now be given "
                f"{role.mention}."
            ),
            ephemeral=True,
        )

    @verification_group.command(
        name="approved-remove-role",
        description=(
            "Set the role removed from users when "
            "their verification is approved."
        ),
    )
    @app_commands.guild_only()
    async def verification_approved_remove_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(
            self.bot,
            "guild_settings",
            None,
        )

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        settings_store.set_approved_remove_role_id(
            interaction.guild.id,
            role.id,
        )

        await interaction.response.send_message(
            (
                "Approved users will now have "
                f"{role.mention} removed."
            ),
            ephemeral=True,
        )

    @verification_group.command(
        name="clear-approved-add-role",
        description=(
            "Clear the role given to users when "
            "their verification is approved."
        ),
    )
    @app_commands.guild_only()
    async def verification_clear_approved_add_role(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(
            self.bot,
            "guild_settings",
            None,
        )

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        settings_store.clear_approved_add_role_id(
            interaction.guild.id
        )

        await interaction.response.send_message(
            "Approved add-role cleared.",
            ephemeral=True,
        )

    @verification_group.command(
        name="clear-approved-remove-role",
        description=(
            "Clear the role removed from users when "
            "their verification is approved."
        ),
    )
    @app_commands.guild_only()
    async def verification_clear_approved_remove_role(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(
            self.bot,
            "guild_settings",
            None,
        )

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        settings_store.clear_approved_remove_role_id(
            interaction.guild.id
        )

        await interaction.response.send_message(
            "Approved remove-role cleared.",
            ephemeral=True,
        )

    @verification_group.command(
        name="automod-enabled",
        description=(
            "Enable or disable verification "
            "application automod banning."
        ),
    )
    @app_commands.guild_only()
    async def verification_automod_enabled(
        self,
        interaction: discord.Interaction,
        enabled: bool,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(
            self.bot,
            "guild_settings",
            None,
        )

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        settings_store.set_automod_enabled(
            interaction.guild.id,
            enabled,
        )

        await interaction.response.send_message(
            (
                "Verification automod is now "
                f"`{'enabled' if enabled else 'disabled'}`."
            ),
            ephemeral=True,
        )

    @verification_group.command(
        name="automod-add",
        description=(
            "Add a blocked term for verification "
            "application automod."
        ),
    )
    @app_commands.guild_only()
    async def verification_automod_add(
        self,
        interaction: discord.Interaction,
        term: str,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(
            self.bot,
            "guild_settings",
            None,
        )

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        try:
            settings_store.add_automod_term(
                interaction.guild.id,
                term,
            )

        except ValueError as error:
            await interaction.response.send_message(
                str(error),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Automod term added.",
            ephemeral=True,
        )

    @verification_group.command(
        name="automod-remove",
        description=(
            "Remove a blocked term from verification "
            "application automod."
        ),
    )
    @app_commands.guild_only()
    async def verification_automod_remove(
        self,
        interaction: discord.Interaction,
        term: str,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(
            self.bot,
            "guild_settings",
            None,
        )

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        removed = (
            settings_store.remove_automod_term(
                interaction.guild.id,
                term,
            )
        )

        await interaction.response.send_message(
            (
                "Automod term removed."
                if removed
                else "That term was not configured."
            ),
            ephemeral=True,
        )

    @verification_group.command(
        name="automod-list",
        description=(
            "List configured verification application "
            "automod terms."
        ),
    )
    @app_commands.guild_only()
    async def verification_automod_list(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(
            self.bot,
            "guild_settings",
            None,
        )

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        terms = (
            settings_store.list_automod_terms(
                interaction.guild.id
            )
        )

        enabled = (
            settings_store.is_automod_enabled(
                interaction.guild.id
            )
        )

        if not terms:
            await interaction.response.send_message(
                (
                    "Verification automod is "
                    f"`{'enabled' if enabled else 'disabled'}`, "
                    "but no terms are configured."
                ),
                ephemeral=True,
            )
            return

        formatted_terms = "\n".join(
            (
                "- "
                f"`{discord.utils.escape_markdown(term)}`"
            )
            for term in terms[:50]
        )

        await interaction.response.send_message(
            (
                "Verification automod is "
                f"`{'enabled' if enabled else 'disabled'}`."
                "\n\n"
                f"{formatted_terms}"
            ),
            ephemeral=True,
        )

    @verification_group.command(
        name="cancel-user",
        description=(
            "Cancel/reset a pending verification "
            "application by user ID."
        ),
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user_id=(
            "Discord user ID with a pending application."
        ),
        confirm="Type CANCEL to confirm.",
        reason=(
            "Optional reason stored in the cancellation log."
        ),
    )
    async def verification_cancel_user(
        self,
        interaction: discord.Interaction,
        user_id: str,
        confirm: str,
        reason: str | None = None,
    ) -> None:
        assert interaction.guild is not None

        if confirm.strip() != "CANCEL":
            await interaction.response.send_message(
                (
                    "Type `CANCEL` in the confirm "
                    "field to cancel an application."
                ),
                ephemeral=True,
            )
            return

        try:
            parsed_user_id = int(
                user_id.strip()
            )

        except ValueError:
            await interaction.response.send_message(
                "That is not a valid Discord user ID.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        cancellation_reason = (
            reason.strip()
            if reason and reason.strip()
            else (
                "Manually cancelled by "
                f"{interaction.user}."
            )
        )

        result = (
            await cancel_pending_application_by_user_id(
                client=interaction.client,
                guild_id=interaction.guild.id,
                user_id=parsed_user_id,
                moderator=interaction.user,
                reason=cancellation_reason,
            )
        )

        await interaction.followup.send(
            result.detail,
            ephemeral=True,
        )

    @verification_group.command(
        name="cancel-all",
        description=(
            "Cancel/reset all pending verification "
            "applications in this server."
        ),
    )
    @app_commands.guild_only()
    @app_commands.describe(
        confirm="Type CANCEL to confirm.",
        reason=(
            "Optional reason stored in every "
            "cancellation log."
        ),
    )
    async def verification_cancel_all(
        self,
        interaction: discord.Interaction,
        confirm: str,
        reason: str | None = None,
    ) -> None:
        assert interaction.guild is not None

        if confirm.strip() != "CANCEL":
            await interaction.response.send_message(
                (
                    "Type `CANCEL` in the confirm "
                    "field to cancel all pending "
                    "applications."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        cancellation_reason = (
            reason.strip()
            if reason and reason.strip()
            else (
                "All pending applications manually "
                f"cancelled by {interaction.user}."
            )
        )

        result = (
            await cancel_all_pending_applications_for_guild(
                client=interaction.client,
                guild_id=interaction.guild.id,
                moderator=interaction.user,
                reason=cancellation_reason,
            )
        )

        await interaction.followup.send(
            result.detail,
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
) -> None:
    bot.add_view(
        VerifyView()
    )

    await bot.add_cog(
        VerificationConfigCommand(
            bot
        )
    )
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from src.commands.verification.verification import (
    VerifyView,
    cancel_all_pending_applications_for_guild,
    cancel_pending_application_by_user_id,
)
from src.commands.welcome.welcome import (
    WelcomeEmbedModal,
    WelcomeExtrasModal,
)
from src.services.forms.constants import (
    FORM_KEY_VERIFICATION,
    VERIFICATION_FORM_PATH,
)
from src.services.forms.form_store import (
    FormStore,
    StoredForm,
)


SETUP_TIMEOUT = 900


def get_form_store(
    bot: commands.Bot,
) -> FormStore:
    form_store = getattr(
        bot,
        "form_store",
        None,
    )

    if form_store is None:
        raise RuntimeError(
            "Form store is not available."
        )

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

    choices: list[
        app_commands.Choice[str]
    ] = []

    for form in forms:
        if (
            current
            and current
            not in form.form_key.lower()
        ):
            continue

        choices.append(
            app_commands.Choice(
                name=(
                    f"{form.form_key} - "
                    f"{form.title}"
                ),
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
        embed.set_thumbnail(
            url=thumbnail_url
        )

    elif guild.icon is not None:
        embed.set_thumbnail(
            url=guild.icon.url
        )

    if image_url:
        embed.set_image(
            url=image_url
        )

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
        (
            image,
            "panel_image",
        ),
        (
            thumbnail,
            "panel_thumbnail",
        ),
    ):
        if attachment is None:
            continue

        if (
            attachment.content_type
            and not attachment.content_type.startswith(
                "image/"
            )
        ):
            raise RuntimeError(
                f"{attachment.filename} "
                "is not an image attachment."
            )

        filename = (
            make_attachment_filename(
                prefix,
                attachment,
            )
        )

        file = await attachment.to_file(
            filename=filename
        )

        files.append(
            file
        )

        attachment_url = (
            f"attachment://{filename}"
        )

        if prefix == "panel_image":
            image_url = attachment_url

        else:
            thumbnail_url = (
                attachment_url
            )

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


def build_verification_help_embed(
) -> discord.Embed:
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
            "`/verification setup`\n"
            "Opens the interactive verification "
            "configuration panel.\n\n"
            "`/verification status`\n"
            "Shows the current verification configuration.\n\n"
            "`/verification help`\n"
            "Shows this help page."
        ),
        inline=False,
    )

    embed.add_field(
        name="Verification Panel",
        value=(
            "`/verification panel`\n"
            "Posts the public verification panel into a "
            "channel. You can choose the form and optionally "
            "attach a large image or thumbnail.\n\n"
            "A basic panel can also be posted from "
            "`/verification setup`."
        ),
        inline=False,
    )

    embed.add_field(
        name="Channels",
        value=(
            "`/verification review-channel`\n"
            "Sets where submitted applications are "
            "sent for staff review.\n\n"
            "`/verification log-channel`\n"
            "Sets where verification logs are posted."
        ),
        inline=False,
    )

    embed.add_field(
        name="Approval Roles",
        value=(
            "`/verification approved-add-role`\n"
            "Sets the role given after approval.\n\n"
            "`/verification approved-remove-role`\n"
            "Sets the role removed after approval.\n\n"
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
            "Enables or disables verification automod.\n\n"
            "`/verification automod-add`\n"
            "Adds a blocked term.\n\n"
            "`/verification automod-remove`\n"
            "Removes a blocked term.\n\n"
            "`/verification automod-list`\n"
            "Shows configured blocked terms."
        ),
        inline=False,
    )

    embed.add_field(
        name="Application Management",
        value=(
            "`/verification cancel-user`\n"
            "Cancels one pending application.\n\n"
            "`/verification cancel-all`\n"
            "Cancels every pending application."
        ),
        inline=False,
    )

    embed.add_field(
        name="Related Commands",
        value=(
            "`/welcome ...`\n"
            "More detailed welcome-message configuration.\n\n"
            "`/permissions ...`\n"
            "Controls bot command permission levels."
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


async def build_verification_status_embed(
    bot: commands.Bot,
    guild: discord.Guild,
    *,
    setup: bool = False,
) -> discord.Embed:
    settings_store = getattr(
        bot,
        "guild_settings",
        None,
    )

    if settings_store is None:
        raise RuntimeError(
            "Guild settings are not available."
        )

    guild_id = guild.id

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
            bot,
            "invite_tracker_ready",
            False,
        )
    )

    welcome_enabled = False
    welcome_channel_id: int | None = None
    welcome_available = False

    welcome_store = getattr(
        bot,
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
        title=(
            "Verification Setup"
            if setup
            else "Verification Configuration"
        ),
        description=(
            (
                "Use the buttons below to configure "
                "verification for "
                f"**{discord.utils.escape_markdown(guild.name)}**."
            )
            if setup
            else (
                "Current verification settings for "
                f"**{discord.utils.escape_markdown(guild.name)}**."
            )
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
            "Changes made here are saved immediately."
            if setup
            else (
                "Use /verification setup to change "
                "these settings."
            )
        )
    )

    return embed


def build_channels_embed(
    bot: commands.Bot,
    guild: discord.Guild,
) -> discord.Embed:
    settings_store = getattr(
        bot,
        "guild_settings",
        None,
    )

    if settings_store is None:
        raise RuntimeError(
            "Guild settings are not available."
        )

    embed = discord.Embed(
        title="Verification Channels",
        description=(
            "Choose the channels used by the "
            "verification system."
        ),
        colour=discord.Colour.blurple(),
    )

    embed.add_field(
        name="Review Channel",
        value=format_channel(
            guild,
            settings_store.get_review_channel_id(
                guild.id
            ),
        ),
        inline=False,
    )

    embed.add_field(
        name="Log Channel",
        value=format_channel(
            guild,
            settings_store
            .get_application_log_channel_id(
                guild.id
            ),
        ),
        inline=False,
    )

    embed.set_footer(
        text=(
            "Selecting a channel saves it immediately."
        )
    )

    return embed


def build_roles_embed(
    bot: commands.Bot,
    guild: discord.Guild,
) -> discord.Embed:
    settings_store = getattr(
        bot,
        "guild_settings",
        None,
    )

    if settings_store is None:
        raise RuntimeError(
            "Guild settings are not available."
        )

    add_role_id = (
        settings_store
        .get_approved_add_role_id(
            guild.id
        )
    )

    remove_role_id = (
        settings_store
        .get_approved_remove_role_id(
            guild.id
        )
    )

    embed = discord.Embed(
        title="Verification Approval Roles",
        description=(
            "Configure the roles changed when "
            "an application is approved."
        ),
        colour=discord.Colour.blurple(),
    )

    embed.add_field(
        name="Role To Give",
        value=format_role(
            guild,
            add_role_id,
        ),
        inline=False,
    )

    embed.add_field(
        name="Role To Remove",
        value=format_role(
            guild,
            remove_role_id,
        ),
        inline=False,
    )

    embed.set_footer(
        text=(
            "Role changes are saved immediately."
        )
    )

    return embed


def build_automod_embed(
    bot: commands.Bot,
    guild: discord.Guild,
) -> discord.Embed:
    settings_store = getattr(
        bot,
        "guild_settings",
        None,
    )

    if settings_store is None:
        raise RuntimeError(
            "Guild settings are not available."
        )

    enabled = (
        settings_store.is_automod_enabled(
            guild.id
        )
    )

    terms = (
        settings_store.list_automod_terms(
            guild.id
        )
    )

    embed = discord.Embed(
        title="Verification Automod",
        description=(
            "Verification automod checks application "
            "answers for configured blocked terms."
        ),
        colour=(
            discord.Colour.green()
            if enabled
            else discord.Colour.dark_grey()
        ),
    )

    embed.add_field(
        name="Status",
        value=(
            "Enabled"
            if enabled
            else "Disabled"
        ),
        inline=True,
    )

    embed.add_field(
        name="Blocked Terms",
        value=str(
            len(terms)
        ),
        inline=True,
    )

    return embed


async def build_welcome_setup_embed(
    bot: commands.Bot,
    guild: discord.Guild,
) -> discord.Embed:
    welcome_store = getattr(
        bot,
        "welcome_store",
        None,
    )

    if welcome_store is None:
        return discord.Embed(
            title="Welcome Messages",
            description=(
                "The welcome-message service "
                "is not available."
            ),
            colour=discord.Colour.red(),
        )

    settings = await welcome_store.get_settings(
        guild.id
    )

    embed = discord.Embed(
        title="Verification Welcome Message",
        description=(
            "Configure the welcome message sent after "
            "a verification application is approved."
        ),
        colour=(
            discord.Colour.green()
            if settings.enabled
            else discord.Colour.dark_grey()
        ),
    )

    embed.add_field(
        name="Status",
        value=(
            "Enabled"
            if settings.enabled
            else "Disabled"
        ),
        inline=True,
    )

    embed.add_field(
        name="Channel",
        value=format_channel(
            guild,
            settings.channel_id,
        ),
        inline=True,
    )

    embed.set_footer(
        text=(
            "The full /welcome command group "
            "remains available too."
        )
    )

    return embed


def build_invite_tracking_embed(
    bot: commands.Bot,
    guild: discord.Guild,
    *,
    result: str | None = None,
) -> discord.Embed:
    ready = bool(
        getattr(
            bot,
            "invite_tracker_ready",
            False,
        )
    )

    embed = discord.Embed(
        title="Invite Tracking",
        description=(
            "Invite tracking records which invite "
            "was used when a new member joins."
        ),
        colour=(
            discord.Colour.green()
            if ready
            else discord.Colour.orange()
        ),
    )

    embed.add_field(
        name="Bot Invite Cache",
        value=(
            "Ready"
            if ready
            else "Not ready"
        ),
        inline=False,
    )

    if result:
        embed.add_field(
            name="Last Refresh",
            value=result,
            inline=False,
        )

    embed.set_footer(
        text=(
            f"Server: {guild.name}"
        )
    )

    return embed


class OwnedSetupView(
    discord.ui.View
):
    def __init__(
        self,
        *,
        bot: commands.Bot,
        guild: discord.Guild,
        owner_id: int,
    ) -> None:
        super().__init__(
            timeout=SETUP_TIMEOUT
        )

        self.bot = bot
        self.guild = guild
        self.owner_id = owner_id

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            (
                "This setup panel belongs to "
                "the person who opened it."
            ),
            ephemeral=True,
        )

        return False

    async def show_main(
        self,
        interaction: discord.Interaction,
    ) -> None:
        embed = (
            await build_verification_status_embed(
                self.bot,
                self.guild,
                setup=True,
            )
        )

        await interaction.response.edit_message(
            embed=embed,
            view=VerificationSetupView(
                bot=self.bot,
                guild=self.guild,
                owner_id=self.owner_id,
            ),
        )


class ReviewChannelSelect(
    discord.ui.ChannelSelect
):
    def __init__(
        self,
        setup_view: ChannelsSetupView,
    ) -> None:
        super().__init__(
            placeholder="Choose review channel",
            min_values=1,
            max_values=1,
            channel_types=[
                discord.ChannelType.text,
            ],
            row=0,
        )

        self.setup_view = setup_view

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        selected = self.values[0]

        settings_store = getattr(
            self.setup_view.bot,
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
            self.setup_view.guild.id,
            selected.id,
        )

        await interaction.response.edit_message(
            embed=build_channels_embed(
                self.setup_view.bot,
                self.setup_view.guild,
            ),
            view=self.setup_view,
        )


class LogChannelSelect(
    discord.ui.ChannelSelect
):
    def __init__(
        self,
        setup_view: ChannelsSetupView,
    ) -> None:
        super().__init__(
            placeholder="Choose verification log channel",
            min_values=1,
            max_values=1,
            channel_types=[
                discord.ChannelType.text,
            ],
            row=1,
        )

        self.setup_view = setup_view

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        selected = self.values[0]

        settings_store = getattr(
            self.setup_view.bot,
            "guild_settings",
            None,
        )

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        (
            settings_store
            .set_application_log_channel_id(
                self.setup_view.guild.id,
                selected.id,
            )
        )

        await interaction.response.edit_message(
            embed=build_channels_embed(
                self.setup_view.bot,
                self.setup_view.guild,
            ),
            view=self.setup_view,
        )


class ChannelsSetupView(
    OwnedSetupView
):
    def __init__(
        self,
        *,
        bot: commands.Bot,
        guild: discord.Guild,
        owner_id: int,
    ) -> None:
        super().__init__(
            bot=bot,
            guild=guild,
            owner_id=owner_id,
        )

        self.add_item(
            ReviewChannelSelect(
                self
            )
        )

        self.add_item(
            LogChannelSelect(
                self
            )
        )

    @discord.ui.button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def back(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.show_main(
            interaction
        )


class AddRoleSelect(
    discord.ui.RoleSelect
):
    def __init__(
        self,
        setup_view: RolesSetupView,
    ) -> None:
        super().__init__(
            placeholder="Choose role to give",
            min_values=1,
            max_values=1,
            row=0,
        )

        self.setup_view = setup_view

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        role = self.values[0]

        settings_store = getattr(
            self.setup_view.bot,
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
            self.setup_view.guild.id,
            role.id,
        )

        await interaction.response.edit_message(
            embed=build_roles_embed(
                self.setup_view.bot,
                self.setup_view.guild,
            ),
            view=self.setup_view,
        )


class RemoveRoleSelect(
    discord.ui.RoleSelect
):
    def __init__(
        self,
        setup_view: RolesSetupView,
    ) -> None:
        super().__init__(
            placeholder="Choose role to remove",
            min_values=1,
            max_values=1,
            row=1,
        )

        self.setup_view = setup_view

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        role = self.values[0]

        settings_store = getattr(
            self.setup_view.bot,
            "guild_settings",
            None,
        )

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        (
            settings_store
            .set_approved_remove_role_id(
                self.setup_view.guild.id,
                role.id,
            )
        )

        await interaction.response.edit_message(
            embed=build_roles_embed(
                self.setup_view.bot,
                self.setup_view.guild,
            ),
            view=self.setup_view,
        )


class RolesSetupView(
    OwnedSetupView
):
    def __init__(
        self,
        *,
        bot: commands.Bot,
        guild: discord.Guild,
        owner_id: int,
    ) -> None:
        super().__init__(
            bot=bot,
            guild=guild,
            owner_id=owner_id,
        )

        self.add_item(
            AddRoleSelect(
                self
            )
        )

        self.add_item(
            RemoveRoleSelect(
                self
            )
        )

    @discord.ui.button(
        label="Clear Give Role",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def clear_add_role(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
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
            self.guild.id
        )

        await interaction.response.edit_message(
            embed=build_roles_embed(
                self.bot,
                self.guild,
            ),
            view=self,
        )

    @discord.ui.button(
        label="Clear Remove Role",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def clear_remove_role(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
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

        (
            settings_store
            .clear_approved_remove_role_id(
                self.guild.id
            )
        )

        await interaction.response.edit_message(
            embed=build_roles_embed(
                self.bot,
                self.guild,
            ),
            view=self,
        )

    @discord.ui.button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        row=3,
    )
    async def back(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.show_main(
            interaction
        )


class VerificationFormSelect(
    discord.ui.Select
):
    def __init__(
        self,
        setup_view: FormPanelSetupView,
        forms: list[StoredForm],
        current_form_key: str,
    ) -> None:
        options: list[
            discord.SelectOption
        ] = []

        found_current = False

        for form in forms[:25]:
            is_current = (
                form.form_key
                == current_form_key
            )

            if is_current:
                found_current = True

            options.append(
                discord.SelectOption(
                    label=form.title[:100],
                    value=form.form_key,
                    description=(
                        f"Key: {form.form_key}"
                    )[:100],
                    default=is_current,
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label=(
                        "Verification Application"
                    ),
                    value=(
                        FORM_KEY_VERIFICATION
                    ),
                    description=(
                        "Default verification form"
                    ),
                    default=True,
                )
            )

        elif (
            not found_current
            and len(options) < 25
        ):
            options.insert(
                0,
                discord.SelectOption(
                    label=current_form_key[:100],
                    value=current_form_key,
                    description=(
                        "Currently configured form"
                    ),
                    default=True,
                ),
            )

        super().__init__(
            placeholder=(
                "Choose active verification form"
            ),
            min_values=1,
            max_values=1,
            options=options[:25],
            row=0,
        )

        self.setup_view = setup_view

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        form_key = self.values[0]

        settings_store = getattr(
            self.setup_view.bot,
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
            self.setup_view.guild.id,
            form_key,
        )

        self.setup_view.current_form_key = (
            form_key
        )

        await interaction.response.edit_message(
            embed=self.setup_view.build_embed(),
            view=self.setup_view,
        )


class PanelChannelSelect(
    discord.ui.ChannelSelect
):
    def __init__(
        self,
        setup_view: FormPanelSetupView,
    ) -> None:
        super().__init__(
            placeholder=(
                "Choose channel for verification panel"
            ),
            min_values=1,
            max_values=1,
            channel_types=[
                discord.ChannelType.text,
            ],
            row=1,
        )

        self.setup_view = setup_view

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        channel = self.values[0]

        self.setup_view.panel_channel_id = (
            channel.id
        )

        await interaction.response.edit_message(
            embed=self.setup_view.build_embed(),
            view=self.setup_view,
        )


class FormPanelSetupView(
    OwnedSetupView
):
    def __init__(
        self,
        *,
        bot: commands.Bot,
        guild: discord.Guild,
        owner_id: int,
        forms: list[StoredForm],
        current_form_key: str,
    ) -> None:
        super().__init__(
            bot=bot,
            guild=guild,
            owner_id=owner_id,
        )

        self.current_form_key = (
            current_form_key
        )

        self.panel_channel_id: (
            int | None
        ) = None

        self.add_item(
            VerificationFormSelect(
                self,
                forms,
                current_form_key,
            )
        )

        self.add_item(
            PanelChannelSelect(
                self
            )
        )

    def build_embed(
        self,
    ) -> discord.Embed:
        embed = discord.Embed(
            title="Verification Form / Panel",
            description=(
                "Choose the active verification form. "
                "You can also post a basic verification "
                "panel directly from here."
            ),
            colour=discord.Colour.blurple(),
        )

        embed.add_field(
            name="Active Form",
            value=(
                f"`{self.current_form_key}`"
            ),
            inline=False,
        )

        embed.add_field(
            name="Panel Destination",
            value=(
                format_channel(
                    self.guild,
                    self.panel_channel_id,
                )
                if self.panel_channel_id
                is not None
                else "`Choose a channel below`"
            ),
            inline=False,
        )

        embed.set_footer(
            text=(
                "Use /verification panel if you "
                "want to attach custom images."
            )
        )

        return embed

    @discord.ui.button(
        label="Post Basic Panel",
        style=discord.ButtonStyle.primary,
        row=2,
    )
    async def post_panel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self.panel_channel_id is None:
            await interaction.response.send_message(
                (
                    "Choose a panel destination "
                    "channel first."
                ),
                ephemeral=True,
            )
            return

        channel = self.guild.get_channel(
            self.panel_channel_id
        )

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            await interaction.response.send_message(
                (
                    "The selected panel channel "
                    "could not be found."
                ),
                ephemeral=True,
            )
            return

        form_store = get_form_store(
            self.bot
        )

        try:
            form_config = (
                await form_store
                .get_form_config(
                    guild_id=self.guild.id,
                    form_key=(
                        self.current_form_key
                    ),
                    fallback_json_path=(
                        VERIFICATION_FORM_PATH
                    ),
                )
            )

            await channel.send(
                embed=build_verify_embed(
                    guild=self.guild,
                    form_title=(
                        form_config.title
                    ),
                ),
                view=VerifyView(),
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

        await interaction.response.send_message(
            (
                "Verification panel posted in "
                f"{channel.mention}."
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def back(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.show_main(
            interaction
        )


class AutomodTermsModal(
    discord.ui.Modal
):
    def __init__(
        self,
        *,
        bot: commands.Bot,
        guild: discord.Guild,
        mode: str,
    ) -> None:
        self.bot = bot
        self.guild = guild
        self.mode = mode

        super().__init__(
            title=(
                "Add Automod Terms"
                if mode == "add"
                else "Remove Automod Terms"
            )
        )

        self.terms = (
            discord.ui.TextInput(
                label=(
                    "Blocked terms"
                    if mode == "add"
                    else "Terms to remove"
                ),
                placeholder=(
                    "One term per line"
                ),
                style=(
                    discord.TextStyle.paragraph
                ),
                required=True,
                max_length=4000,
            )
        )

        self.add_item(
            self.terms
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
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

        terms = [
            line.strip()
            for line
            in str(
                self.terms.value
            ).splitlines()
            if line.strip()
        ]

        if not terms:
            await interaction.response.send_message(
                "No terms were provided.",
                ephemeral=True,
            )
            return

        if self.mode == "add":
            added = (
                settings_store
                .add_automod_terms(
                    self.guild.id,
                    terms,
                )
            )

            await interaction.response.send_message(
                (
                    f"Added **{added}** new "
                    "automod term(s)."
                ),
                ephemeral=True,
            )

            return

        removed = 0

        for term in terms:
            if (
                settings_store
                .remove_automod_term(
                    self.guild.id,
                    term,
                )
            ):
                removed += 1

        await interaction.response.send_message(
            (
                f"Removed **{removed}** "
                "automod term(s)."
            ),
            ephemeral=True,
        )


class AutomodSetupView(
    OwnedSetupView
):
    @discord.ui.button(
        label="Toggle",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def toggle(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
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

        current = (
            settings_store
            .is_automod_enabled(
                self.guild.id
            )
        )

        settings_store.set_automod_enabled(
            self.guild.id,
            not current,
        )

        await interaction.response.edit_message(
            embed=build_automod_embed(
                self.bot,
                self.guild,
            ),
            view=self,
        )

    @discord.ui.button(
        label="Add Terms",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def add_terms(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(
            AutomodTermsModal(
                bot=self.bot,
                guild=self.guild,
                mode="add",
            )
        )

    @discord.ui.button(
        label="Remove Terms",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def remove_terms(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(
            AutomodTermsModal(
                bot=self.bot,
                guild=self.guild,
                mode="remove",
            )
        )

    @discord.ui.button(
        label="View Terms",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def view_terms(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
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
            settings_store
            .list_automod_terms(
                self.guild.id
            )
        )

        if not terms:
            description = (
                "No blocked terms are configured."
            )

        else:
            shown_terms = terms[:40]

            description = "\n".join(
                (
                    f"• `{discord.utils.escape_markdown(term[:80])}`"
                )
                for term in shown_terms
            )

            if len(terms) > len(shown_terms):
                description += (
                    "\n\n"
                    f"Plus {len(terms) - len(shown_terms)} "
                    "more."
                )

        embed = discord.Embed(
            title="Verification Automod Terms",
            description=description,
            colour=discord.Colour.blurple(),
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @discord.ui.button(
        label="Add Default Terms",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def add_defaults(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
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

        added = (
            settings_store
            .add_default_automod_terms(
                self.guild.id
            )
        )

        await interaction.response.send_message(
            (
                f"Added **{added}** default "
                "automod term(s)."
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def back(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.show_main(
            interaction
        )


class WelcomeChannelSelect(
    discord.ui.ChannelSelect
):
    def __init__(
        self,
        setup_view: WelcomeSetupView,
    ) -> None:
        super().__init__(
            placeholder="Choose welcome channel",
            min_values=1,
            max_values=1,
            channel_types=[
                discord.ChannelType.text,
            ],
            row=0,
        )

        self.setup_view = setup_view

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        welcome_store = getattr(
            self.setup_view.bot,
            "welcome_store",
            None,
        )

        if welcome_store is None:
            await interaction.response.send_message(
                (
                    "The welcome-message service "
                    "is not available."
                ),
                ephemeral=True,
            )
            return

        channel = self.values[0]

        await welcome_store.set_channel(
            guild_id=(
                self.setup_view.guild.id
            ),
            channel_id=channel.id,
        )

        await interaction.response.edit_message(
            embed=(
                await build_welcome_setup_embed(
                    self.setup_view.bot,
                    self.setup_view.guild,
                )
            ),
            view=self.setup_view,
        )


class WelcomeSetupView(
    OwnedSetupView
):
    def __init__(
        self,
        *,
        bot: commands.Bot,
        guild: discord.Guild,
        owner_id: int,
    ) -> None:
        super().__init__(
            bot=bot,
            guild=guild,
            owner_id=owner_id,
        )

        self.add_item(
            WelcomeChannelSelect(
                self
            )
        )

    @discord.ui.button(
        label="Enable / Disable",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def toggle(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        welcome_store = getattr(
            self.bot,
            "welcome_store",
            None,
        )

        if welcome_store is None:
            await interaction.response.send_message(
                (
                    "The welcome-message service "
                    "is not available."
                ),
                ephemeral=True,
            )
            return

        settings = (
            await welcome_store.get_settings(
                self.guild.id
            )
        )

        if (
            not settings.enabled
            and settings.channel_id is None
        ):
            await interaction.response.send_message(
                (
                    "Choose a welcome channel "
                    "before enabling welcome messages."
                ),
                ephemeral=True,
            )
            return

        await welcome_store.set_enabled(
            guild_id=self.guild.id,
            enabled=(
                not settings.enabled
            ),
        )

        await interaction.response.edit_message(
            embed=(
                await build_welcome_setup_embed(
                    self.bot,
                    self.guild,
                )
            ),
            view=self,
        )

    @discord.ui.button(
        label="Edit Embed",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def edit_embed(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        welcome_store = getattr(
            self.bot,
            "welcome_store",
            None,
        )

        if welcome_store is None:
            await interaction.response.send_message(
                (
                    "The welcome-message service "
                    "is not available."
                ),
                ephemeral=True,
            )
            return

        settings = (
            await welcome_store.get_settings(
                self.guild.id
            )
        )

        await interaction.response.send_modal(
            WelcomeEmbedModal(
                store=welcome_store,
                guild=self.guild,
                settings=settings,
                title=(
                    "Edit Welcome Message"
                ),
            )
        )

    @discord.ui.button(
        label="Embed Extras",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def edit_extras(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        welcome_store = getattr(
            self.bot,
            "welcome_store",
            None,
        )

        if welcome_store is None:
            await interaction.response.send_message(
                (
                    "The welcome-message service "
                    "is not available."
                ),
                ephemeral=True,
            )
            return

        settings = (
            await welcome_store.get_settings(
                self.guild.id
            )
        )

        await interaction.response.send_modal(
            WelcomeExtrasModal(
                store=welcome_store,
                guild=self.guild,
                settings=settings,
            )
        )

    @discord.ui.button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def back(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.show_main(
            interaction
        )


class InviteTrackingSetupView(
    OwnedSetupView
):
    @discord.ui.button(
        label="Refresh Invites",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def refresh_invites(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        invite_tracker = getattr(
            self.bot,
            "invite_tracker",
            None,
        )

        if invite_tracker is None:
            await interaction.response.send_message(
                (
                    "The invite tracker "
                    "is not available."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        try:
            refreshed = (
                await invite_tracker
                .sync_guild_invites(
                    self.guild
                )
            )

            result = (
                "Invite cache refreshed successfully."
                if refreshed
                else (
                    "Invite cache could not be refreshed. "
                    "Check the bot's invite permissions."
                )
            )

        except Exception as error:
            result = (
                "Invite refresh failed: "
                f"`{error}`"
            )

        await interaction.edit_original_response(
            embed=build_invite_tracking_embed(
                self.bot,
                self.guild,
                result=result,
            ),
            view=self,
        )

    @discord.ui.button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def back(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.show_main(
            interaction
        )


class VerificationSetupView(
    OwnedSetupView
):
    @discord.ui.button(
        label="Channels",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def channels(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        view = ChannelsSetupView(
            bot=self.bot,
            guild=self.guild,
            owner_id=self.owner_id,
        )

        await interaction.response.edit_message(
            embed=build_channels_embed(
                self.bot,
                self.guild,
            ),
            view=view,
        )

    @discord.ui.button(
        label="Approval Roles",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def approval_roles(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        view = RolesSetupView(
            bot=self.bot,
            guild=self.guild,
            owner_id=self.owner_id,
        )

        await interaction.response.edit_message(
            embed=build_roles_embed(
                self.bot,
                self.guild,
            ),
            view=view,
        )

    @discord.ui.button(
        label="Form / Panel",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def form_panel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
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

        form_store = get_form_store(
            self.bot
        )

        forms = await form_store.list_forms(
            self.guild.id
        )

        current_form_key = (
            settings_store
            .get_verification_form_key(
                self.guild.id
            )
            or FORM_KEY_VERIFICATION
        )

        view = FormPanelSetupView(
            bot=self.bot,
            guild=self.guild,
            owner_id=self.owner_id,
            forms=forms,
            current_form_key=(
                current_form_key
            ),
        )

        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view,
        )

    @discord.ui.button(
        label="Automod",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def automod(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        view = AutomodSetupView(
            bot=self.bot,
            guild=self.guild,
            owner_id=self.owner_id,
        )

        await interaction.response.edit_message(
            embed=build_automod_embed(
                self.bot,
                self.guild,
            ),
            view=view,
        )

    @discord.ui.button(
        label="Welcome",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def welcome(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        view = WelcomeSetupView(
            bot=self.bot,
            guild=self.guild,
            owner_id=self.owner_id,
        )

        await interaction.response.edit_message(
            embed=(
                await build_welcome_setup_embed(
                    self.bot,
                    self.guild,
                )
            ),
            view=view,
        )

    @discord.ui.button(
        label="Invite Tracking",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def invite_tracking(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        view = InviteTrackingSetupView(
            bot=self.bot,
            guild=self.guild,
            owner_id=self.owner_id,
        )

        await interaction.response.edit_message(
            embed=build_invite_tracking_embed(
                self.bot,
                self.guild,
            ),
            view=view,
        )

    @discord.ui.button(
        label="Refresh",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def refresh(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        embed = (
            await build_verification_status_embed(
                self.bot,
                self.guild,
                setup=True,
            )
        )

        await interaction.response.edit_message(
            embed=embed,
            view=self,
        )


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
        name="setup",
        description=(
            "Open the interactive verification setup panel."
        ),
    )
    @app_commands.guild_only()
    async def verification_setup(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        try:
            embed = (
                await build_verification_status_embed(
                    self.bot,
                    interaction.guild,
                    setup=True,
                )
            )

        except Exception as error:
            await interaction.response.send_message(
                (
                    "Could not load verification "
                    f"configuration: `{error}`"
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=embed,
            view=VerificationSetupView(
                bot=self.bot,
                guild=interaction.guild,
                owner_id=interaction.user.id,
            ),
            ephemeral=True,
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

        try:
            embed = (
                await build_verification_status_embed(
                    self.bot,
                    interaction.guild,
                )
            )

        except Exception as error:
            await interaction.response.send_message(
                (
                    "Could not load verification "
                    f"configuration: `{error}`"
                ),
                ephemeral=True,
            )
            return

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
            ) = (
                await build_panel_attachment_files(
                    image=image,
                    thumbnail=thumbnail,
                )
            )

            await channel.send(
                embed=build_verify_embed(
                    guild=interaction.guild,
                    form_title=form_config.title,
                    image_url=image_url,
                    thumbnail_url=(
                        thumbnail_url
                    ),
                ),
                view=VerifyView(),
                files=(
                    files
                    if files
                    else None
                ),
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

        (
            settings_store
            .set_application_log_channel_id(
                interaction.guild.id,
                channel.id,
            )
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
            "Set the role given to users when "
            "their verification is approved."
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

        (
            settings_store
            .set_approved_add_role_id(
                interaction.guild.id,
                role.id,
            )
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

        (
            settings_store
            .set_approved_remove_role_id(
                interaction.guild.id,
                role.id,
            )
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

        (
            settings_store
            .clear_approved_add_role_id(
                interaction.guild.id
            )
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

        (
            settings_store
            .clear_approved_remove_role_id(
                interaction.guild.id
            )
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
            settings_store
            .remove_automod_term(
                interaction.guild.id,
                term,
            )
        )

        await interaction.response.send_message(
            (
                "Automod term removed."
                if removed
                else (
                    "That term was not "
                    "configured."
                )
            ),
            ephemeral=True,
        )

    @verification_group.command(
        name="automod-list",
        description=(
            "List configured verification "
            "application automod terms."
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
            settings_store
            .list_automod_terms(
                interaction.guild.id
            )
        )

        enabled = (
            settings_store
            .is_automod_enabled(
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
            "Discord user ID with a "
            "pending application."
        ),
        confirm=(
            "Type CANCEL to confirm."
        ),
        reason=(
            "Optional reason stored in "
            "the cancellation log."
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
                    "Type `CANCEL` in the "
                    "confirm field to cancel "
                    "an application."
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
                (
                    "That is not a valid "
                    "Discord user ID."
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
            if reason
            and reason.strip()
            else (
                "Manually cancelled by "
                f"{interaction.user}."
            )
        )

        result = (
            await cancel_pending_application_by_user_id(
                client=interaction.client,
                guild_id=(
                    interaction.guild.id
                ),
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
        confirm=(
            "Type CANCEL to confirm."
        ),
        reason=(
            "Optional reason stored in "
            "every cancellation log."
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
                    "Type `CANCEL` in the "
                    "confirm field to cancel "
                    "all pending applications."
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
            if reason
            and reason.strip()
            else (
                "All pending applications "
                "manually cancelled by "
                f"{interaction.user}."
            )
        )

        result = (
            await cancel_all_pending_applications_for_guild(
                client=interaction.client,
                guild_id=(
                    interaction.guild.id
                ),
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
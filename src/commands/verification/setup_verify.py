from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from src.commands.verification.verification import (
    VerifyView,
    cancel_all_pending_applications_for_guild,
    cancel_pending_application_by_user_id,
)
from src.services.forms.constants import FORM_KEY_VERIFICATION, VERIFICATION_FORM_PATH
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

    form_store = getattr(interaction.client, "form_store", None)

    if form_store is None:
        return []

    forms = await form_store.list_forms(interaction.guild.id)
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
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{guild.name} Verification",
        description=(
            "Welcome!\n\n"
            f"Please complete the **{discord.utils.escape_markdown(form_title)}** form "
            "to apply for access to the server.\n\n"
            "Click the button below to begin."
        ),
        colour=discord.Colour.blurple(),
    )

    if guild.icon is not None:
        embed.set_thumbnail(url=guild.icon.url)

    embed.set_footer(text="TFSBot Verification")

    return embed


class VerificationConfigCommand(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    verification_group = app_commands.Group(
        name="verification",
        description="Configure verification settings.",
    )

    @verification_group.command(
        name="panel",
        description="Post the verification panel using a selected form.",
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(form=form_key_autocomplete)
    async def verification_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        form: str = FORM_KEY_VERIFICATION,
    ) -> None:
        assert interaction.guild is not None

        form_key = form.lower().strip()
        form_store = get_form_store(self.bot)

        try:
            form_config = await form_store.get_form_config(
                guild_id=interaction.guild.id,
                form_key=form_key,
                fallback_json_path=VERIFICATION_FORM_PATH,
            )

        except Exception as error:
            await interaction.response.send_message(
                f"Could not load form `{form_key}`: `{error}`",
                ephemeral=True,
            )
            return

        settings_store = getattr(self.bot, "guild_settings", None)

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

        await channel.send(
            embed=build_verify_embed(
                guild=interaction.guild,
                form_title=form_config.title,
            ),
            view=VerifyView(),
        )

        await interaction.response.send_message(
            f"Verification panel posted in {channel.mention} using form `{form_key}`.",
            ephemeral=True,
        )

    @verification_group.command(
        name="review-channel",
        description="Set the channel where verification applications are reviewed.",
    )
    @app_commands.guild_only()
    async def verification_review_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(self.bot, "guild_settings", None)

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        settings_store.set_review_channel_id(interaction.guild.id, channel.id)

        await interaction.response.send_message(
            f"Verification review channel set to {channel.mention}.",
            ephemeral=True,
        )

    @verification_group.command(
        name="log-channel",
        description="Set the channel where verification application logs are posted.",
    )
    @app_commands.guild_only()
    async def verification_log_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(self.bot, "guild_settings", None)

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        settings_store.set_application_log_channel_id(interaction.guild.id, channel.id)

        await interaction.response.send_message(
            f"Verification log channel set to {channel.mention}.",
            ephemeral=True,
        )


    @verification_group.command(
        name="approved-add-role",
        description="Set the role given to users when their verification is approved.",
    )
    @app_commands.guild_only()
    async def verification_approved_add_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(self.bot, "guild_settings", None)

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        settings_store.set_approved_add_role_id(interaction.guild.id, role.id)

        await interaction.response.send_message(
            f"Approved users will now be given {role.mention}.",
            ephemeral=True,
        )

    @verification_group.command(
        name="approved-remove-role",
        description="Set the role removed from users when their verification is approved.",
    )
    @app_commands.guild_only()
    async def verification_approved_remove_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(self.bot, "guild_settings", None)

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        settings_store.set_approved_remove_role_id(interaction.guild.id, role.id)

        await interaction.response.send_message(
            f"Approved users will now have {role.mention} removed.",
            ephemeral=True,
        )

    @verification_group.command(
        name="clear-approved-add-role",
        description="Clear the role given to users when their verification is approved.",
    )
    @app_commands.guild_only()
    async def verification_clear_approved_add_role(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(self.bot, "guild_settings", None)

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        settings_store.clear_approved_add_role_id(interaction.guild.id)

        await interaction.response.send_message(
            "Approved add-role cleared.",
            ephemeral=True,
        )

    @verification_group.command(
        name="clear-approved-remove-role",
        description="Clear the role removed from users when their verification is approved.",
    )
    @app_commands.guild_only()
    async def verification_clear_approved_remove_role(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(self.bot, "guild_settings", None)

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        settings_store.clear_approved_remove_role_id(interaction.guild.id)

        await interaction.response.send_message(
            "Approved remove-role cleared.",
            ephemeral=True,
        )

    @verification_group.command(
        name="automod-enabled",
        description="Enable or disable verification application automod banning.",
    )
    @app_commands.guild_only()
    async def verification_automod_enabled(
        self,
        interaction: discord.Interaction,
        enabled: bool,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(self.bot, "guild_settings", None)

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        settings_store.set_automod_enabled(interaction.guild.id, enabled)

        await interaction.response.send_message(
            f"Verification automod is now `{'enabled' if enabled else 'disabled'}`.",
            ephemeral=True,
        )

    @verification_group.command(
        name="automod-add",
        description="Add a blocked term for verification application automod.",
    )
    @app_commands.guild_only()
    async def verification_automod_add(
        self,
        interaction: discord.Interaction,
        term: str,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(self.bot, "guild_settings", None)

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        try:
            settings_store.add_automod_term(interaction.guild.id, term)
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await interaction.response.send_message(
            "Automod term added.",
            ephemeral=True,
        )

    @verification_group.command(
        name="automod-remove",
        description="Remove a blocked term from verification application automod.",
    )
    @app_commands.guild_only()
    async def verification_automod_remove(
        self,
        interaction: discord.Interaction,
        term: str,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(self.bot, "guild_settings", None)

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        removed = settings_store.remove_automod_term(interaction.guild.id, term)

        await interaction.response.send_message(
            "Automod term removed." if removed else "That term was not configured.",
            ephemeral=True,
        )

    @verification_group.command(
        name="automod-list",
        description="List configured verification application automod terms.",
    )
    @app_commands.guild_only()
    async def verification_automod_list(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        settings_store = getattr(self.bot, "guild_settings", None)

        if settings_store is None:
            await interaction.response.send_message(
                "Guild settings are not available.",
                ephemeral=True,
            )
            return

        terms = settings_store.list_automod_terms(interaction.guild.id)
        enabled = settings_store.is_automod_enabled(interaction.guild.id)

        if not terms:
            await interaction.response.send_message(
                f"Verification automod is `{'enabled' if enabled else 'disabled'}`, but no terms are configured.",
                ephemeral=True,
            )
            return

        formatted_terms = "\n".join(f"- `{discord.utils.escape_markdown(term)}`" for term in terms[:50])

        await interaction.response.send_message(
            f"Verification automod is `{'enabled' if enabled else 'disabled'}`.\n\n{formatted_terms}",
            ephemeral=True,
        )


    @verification_group.command(
        name="cancel-user",
        description="Cancel/reset a pending verification application by user ID.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user_id="Discord user ID with a pending application.",
        confirm="Type CANCEL to confirm.",
        reason="Optional reason stored in the cancellation log.",
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
                "Type `CANCEL` in the confirm field to cancel an application.",
                ephemeral=True,
            )
            return

        try:
            parsed_user_id = int(user_id.strip())
        except ValueError:
            await interaction.response.send_message(
                "That is not a valid Discord user ID.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        cancellation_reason = (
            reason.strip()
            if reason and reason.strip()
            else f"Manually cancelled by {interaction.user}."
        )

        result = await cancel_pending_application_by_user_id(
            client=interaction.client,
            guild_id=interaction.guild.id,
            user_id=parsed_user_id,
            moderator=interaction.user,
            reason=cancellation_reason,
        )

        await interaction.followup.send(result.detail, ephemeral=True)

    @verification_group.command(
        name="cancel-all",
        description="Cancel/reset all pending verification applications in this server.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        confirm="Type CANCEL to confirm.",
        reason="Optional reason stored in every cancellation log.",
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
                "Type `CANCEL` in the confirm field to cancel all pending applications.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        cancellation_reason = (
            reason.strip()
            if reason and reason.strip()
            else f"All pending applications manually cancelled by {interaction.user}."
        )

        result = await cancel_all_pending_applications_for_guild(
            client=interaction.client,
            guild_id=interaction.guild.id,
            moderator=interaction.user,
            reason=cancellation_reason,
        )

        await interaction.followup.send(result.detail, ephemeral=True)



async def setup(bot: commands.Bot) -> None:
    bot.add_view(VerifyView())
    await bot.add_cog(VerificationConfigCommand(bot))
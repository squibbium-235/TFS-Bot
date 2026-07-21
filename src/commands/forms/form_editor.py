from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from src.commands.forms.form_runtime import GenericFormStartView
from src.services.forms.constants import (
    FORM_KEY_VERIFICATION,
    VERIFICATION_FORM_PATH,
)
from src.services.forms.form_store import FormStore
from src.services.forms.models import StoredFormQuestion


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

    current = current.lower().strip()
    forms = await form_store.list_forms(interaction.guild.id)

    choices: list[app_commands.Choice[str]] = []

    verification_exists = any(
        form.form_key == FORM_KEY_VERIFICATION
        for form in forms
    )

    if not verification_exists:
        choices.append(
            app_commands.Choice(
                name="verification - Verification",
                value=FORM_KEY_VERIFICATION,
            )
        )

    for form in forms:
        label = f"{form.form_key} - {form.title}"

        if current and current not in label.lower():
            continue

        choices.append(
            app_commands.Choice(
                name=label[:100],
                value=form.form_key,
            )
        )

    return choices[:25]


def question_style_label(style: str) -> str:
    if style == "short":
        return "Short answer"

    if style == "paragraph":
        return "Paragraph"

    return style


def yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def build_questions_embeds(
    guild: discord.Guild,
    form_key: str,
    form_title: str,
    questions: list[StoredFormQuestion],
) -> list[discord.Embed]:
    total_questions = len(questions)
    total_modal_pages = max(1, (total_questions + 4) // 5)

    embeds: list[discord.Embed] = []

    chunks = [
        questions[index:index + 20]
        for index in range(0, len(questions), 20)
    ]

    if not chunks:
        embed = discord.Embed(
            title=f"Form: {form_key}",
            description=(
                f"**Title:** {discord.utils.escape_markdown(form_title)}\n"
                f"**Server:** {discord.utils.escape_markdown(guild.name)}\n"
                "**Questions:** `0`\n"
                "**Modal Pages:** `0`\n\n"
                "This form has no questions yet.\n"
                "Add one with `/form add`."
            ),
            colour=discord.Colour.blurple(),
        )

        if guild.icon is not None:
            embed.set_thumbnail(url=guild.icon.url)

        embeds.append(embed)
        return embeds

    for chunk_index, chunk in enumerate(chunks, start=1):
        embed = discord.Embed(
            title=f"Form: {form_key}",
            colour=discord.Colour.blurple(),
        )

        if chunk_index == 1:
            embed.description = (
                f"**Title:** {discord.utils.escape_markdown(form_title)}\n"
                f"**Server:** {discord.utils.escape_markdown(guild.name)}\n"
                f"**Questions:** `{total_questions}`\n"
                f"**Modal Pages:** `{total_modal_pages}`\n\n"
                "Use the **key** when editing, deleting, or moving questions."
            )

            if guild.icon is not None:
                embed.set_thumbnail(url=guild.icon.url)

        else:
            embed.description = "Continued question list."

        for question in chunk:
            placeholder = question.placeholder or "None"

            min_length = (
                str(question.min_length)
                if question.min_length is not None
                else "None"
            )

            max_length = (
                str(question.max_length)
                if question.max_length is not None
                else "None"
            )

            embed.add_field(
                name=f"{question.sort_order}. {question.question_key}"[:256],
                value=(
                    f"**Question:** {discord.utils.escape_markdown(question.label)}\n"
                    f"**Type:** `{question_style_label(question.style)}`\n"
                    f"**Required:** `{yes_no(question.required)}`\n"
                    f"**Placeholder:** `{discord.utils.escape_markdown(placeholder)}`\n"
                    f"**Length:** min `{min_length}` / max `{max_length}`"
                )[:1024],
                inline=False,
            )

        embed.set_footer(
            text=f"Showing {len(chunk)} question(s), embed {chunk_index}/{len(chunks)}"
        )

        embeds.append(embed)

    return embeds[:10]


class FormEditorCommand(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    form_group = app_commands.Group(
        name="form",
        description="Manage and publish forms.",
    )

    @form_group.command(
        name="create",
        description="Create a new form.",
    )
    @app_commands.guild_only()

    async def create_form(
        self,
        interaction: discord.Interaction,
        key: str,
        title: str,
    ) -> None:
        assert interaction.guild is not None

        form_store = get_form_store(self.bot)

        try:
            await form_store.create_form(
                guild_id=interaction.guild.id,
                form_key=key,
                title=title,
            )

        except Exception as error:
            await interaction.response.send_message(
                f"Could not create form: `{error}`",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Created form `{key.lower().strip()}`.",
            ephemeral=True,
        )

    @form_group.command(
        name="list",
        description="List all forms.",
    )
    @app_commands.guild_only()

    async def list_forms(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        form_store = get_form_store(self.bot)
        forms = await form_store.list_forms(interaction.guild.id)

        if not forms:
            await interaction.response.send_message(
                "No forms exist yet. Create one with `/form create`.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Forms",
            colour=discord.Colour.blurple(),
        )

        for form in forms:
            embed.add_field(
                name=form.form_key,
                value=(
                    f"**Title:** {discord.utils.escape_markdown(form.title)}\n"
                    f"**Updated:** `{form.updated_at}`"
                ),
                inline=False,
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @form_group.command(
        name="view",
        description="View questions in a form.",
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(form=form_key_autocomplete)

    async def view_form(
        self,
        interaction: discord.Interaction,
        form: str,
    ) -> None:
        assert interaction.guild is not None

        form_store = get_form_store(self.bot)
        form_key = form.lower().strip()

        try:
            form_config = await form_store.get_form_config(
                guild_id=interaction.guild.id,
                form_key=form_key,
                fallback_json_path=VERIFICATION_FORM_PATH,
            )

            questions = await form_store.list_questions(
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

        embeds = build_questions_embeds(
            guild=interaction.guild,
            form_key=form_key,
            form_title=form_config.title,
            questions=questions,
        )

        await interaction.response.send_message(
            embeds=embeds,
            ephemeral=True,
        )

    @form_group.command(
        name="preview",
        description="Preview form pages.",
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(form=form_key_autocomplete)

    async def preview_form(
        self,
        interaction: discord.Interaction,
        form: str,
    ) -> None:
        assert interaction.guild is not None

        form_store = get_form_store(self.bot)
        form_key = form.lower().strip()

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

        pages = form_config.pages()

        embed = discord.Embed(
            title=f"Form Preview: {form_key}",
            description=(
                f"**Title:** {discord.utils.escape_markdown(form_config.title)}\n"
                f"**Questions:** `{len(form_config.questions)}`\n"
                f"**Modal Pages:** `{len(pages)}`"
            ),
            colour=discord.Colour.blurple(),
        )

        for index, page in enumerate(pages, start=1):
            embed.add_field(
                name=f"Page {index}",
                value="\n".join(
                    f"`{question.key}` - {discord.utils.escape_markdown(question.label)}"
                    for question in page
                ) or "*No questions.*",
                inline=False,
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @form_group.command(
        name="add",
        description="Add a question to a form.",
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(form=form_key_autocomplete)
    @app_commands.choices(
        style=[
            app_commands.Choice(name="Short answer", value="short"),
            app_commands.Choice(name="Paragraph", value="paragraph"),
        ]
    )
    async def add_question(
        self,
        interaction: discord.Interaction,
        form: str,
        key: str,
        label: str,
        style: app_commands.Choice[str],
        required: bool = True,
        placeholder: str | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
    ) -> None:
        assert interaction.guild is not None

        form_store = get_form_store(self.bot)
        form_key = form.lower().strip()

        try:
            if form_key == FORM_KEY_VERIFICATION:
                await form_store.ensure_form_from_json(
                    guild_id=interaction.guild.id,
                    form_key=FORM_KEY_VERIFICATION,
                    json_path=VERIFICATION_FORM_PATH,
                )

            await form_store.add_question(
                guild_id=interaction.guild.id,
                form_key=form_key,
                question_key=key,
                label=label.strip(),
                style=style.value,
                required=required,
                placeholder=placeholder.strip() if placeholder else None,
                min_length=min_length,
                max_length=max_length,
            )

        except Exception as error:
            await interaction.response.send_message(
                f"Could not add question: `{error}`",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Added question `{key.lower().strip()}` to form `{form_key}`.",
            ephemeral=True,
        )

    @form_group.command(
        name="edit",
        description="Edit a form question.",
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(form=form_key_autocomplete)
    @app_commands.choices(
        style=[
            app_commands.Choice(name="Short answer", value="short"),
            app_commands.Choice(name="Paragraph", value="paragraph"),
        ]
    )
    async def edit_question(
        self,
        interaction: discord.Interaction,
        form: str,
        key: str,
        label: str | None = None,
        style: app_commands.Choice[str] | None = None,
        required: bool | None = None,
        placeholder: str | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        clear_placeholder: bool = False,
        clear_lengths: bool = False,
    ) -> None:
        assert interaction.guild is not None

        form_store = get_form_store(self.bot)
        form_key = form.lower().strip()

        try:
            updated = await form_store.update_question(
                guild_id=interaction.guild.id,
                form_key=form_key,
                question_key=key,
                label=label.strip() if label else None,
                style=style.value if style else None,
                required=required,
                placeholder=placeholder.strip() if placeholder else None,
                min_length=min_length,
                max_length=max_length,
                clear_placeholder=clear_placeholder,
                clear_lengths=clear_lengths,
            )

        except Exception as error:
            await interaction.response.send_message(
                f"Could not edit question: `{error}`",
                ephemeral=True,
            )
            return

        if not updated:
            await interaction.response.send_message(
                f"No question found with key `{key.lower().strip()}`.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Updated question `{key.lower().strip()}` in form `{form_key}`.",
            ephemeral=True,
        )

    @form_group.command(
        name="delete",
        description="Delete a question from a form.",
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(form=form_key_autocomplete)
    async def delete_question(
        self,
        interaction: discord.Interaction,
        form: str,
        key: str,
        confirm: bool = False,
    ) -> None:
        assert interaction.guild is not None

        form_key = form.lower().strip()

        if not confirm:
            await interaction.response.send_message(
                "Set `confirm:true` to delete this question.",
                ephemeral=True,
            )
            return

        form_store = get_form_store(self.bot)

        deleted = await form_store.delete_question(
            guild_id=interaction.guild.id,
            form_key=form_key,
            question_key=key,
        )

        if not deleted:
            await interaction.response.send_message(
                f"No question found with key `{key.lower().strip()}`.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Deleted question `{key.lower().strip()}` from form `{form_key}`.",
            ephemeral=True,
        )

    @form_group.command(
        name="move",
        description="Move a question to a different position.",
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(form=form_key_autocomplete)
    async def move_question(
        self,
        interaction: discord.Interaction,
        form: str,
        key: str,
        position: int,
    ) -> None:
        assert interaction.guild is not None

        form_store = get_form_store(self.bot)
        form_key = form.lower().strip()

        moved = await form_store.move_question(
            guild_id=interaction.guild.id,
            form_key=form_key,
            question_key=key,
            new_position=position,
        )

        if not moved:
            await interaction.response.send_message(
                f"No question found with key `{key.lower().strip()}`.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Moved question `{key.lower().strip()}` to position `{position}` in form `{form_key}`.",
            ephemeral=True,
        )

    @form_group.command(
        name="delete-form",
        description="Delete an entire form.",
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(form=form_key_autocomplete)
    async def delete_form(
        self,
        interaction: discord.Interaction,
        form: str,
        confirm: bool = False,
    ) -> None:
        assert interaction.guild is not None

        form_key = form.lower().strip()

        if form_key == FORM_KEY_VERIFICATION:
            await interaction.response.send_message(
                "You cannot delete the verification form. Use `/form reset-verification` instead.",
                ephemeral=True,
            )
            return

        if not confirm:
            await interaction.response.send_message(
                "Set `confirm:true` to delete this form and all of its questions/submissions.",
                ephemeral=True,
            )
            return

        form_store = get_form_store(self.bot)

        deleted = await form_store.delete_form(
            guild_id=interaction.guild.id,
            form_key=form_key,
        )

        if not deleted:
            await interaction.response.send_message(
                f"No form found with key `{form_key}`.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Deleted form `{form_key}`.",
            ephemeral=True,
        )

    @form_group.command(
        name="reset-verification",
        description="Reset verification form to the built-in default.",
    )
    @app_commands.guild_only()
    async def reset_verification(
        self,
        interaction: discord.Interaction,
        confirm: bool = False,
    ) -> None:
        assert interaction.guild is not None

        if not confirm:
            await interaction.response.send_message(
                "Set `confirm:true` to reset the verification form to the built-in default.",
                ephemeral=True,
            )
            return

        form_store = get_form_store(self.bot)

        await form_store.reset_verification_form_from_json(
            guild_id=interaction.guild.id,
            json_path=VERIFICATION_FORM_PATH,
        )

        await interaction.response.send_message(
            "Verification form reset to the built-in default.",
            ephemeral=True,
        )

    @form_group.command(
        name="publish",
        description="Publish a general form panel.",
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(form=form_key_autocomplete)
    async def publish_form(
        self,
        interaction: discord.Interaction,
        form: str,
        channel: discord.TextChannel,
        title: str,
        description: str,
    ) -> None:
        assert interaction.guild is not None

        form_store = get_form_store(self.bot)
        form_key = form.lower().strip()

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

        embed = discord.Embed(
            title=title,
            description=description,
            colour=discord.Colour.blurple(),
        )

        if interaction.guild.icon is not None:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        embed.set_footer(text=f"Form: {form_config.title}")

        message = await channel.send(
            embed=embed,
            view=GenericFormStartView(),
        )

        await form_store.save_published_form(
            guild_id=interaction.guild.id,
            form_key=form_key,
            channel_id=channel.id,
            message_id=message.id,
            title=title,
            description=description,
        )

        await interaction.response.send_message(
            f"Published form `{form_key}` in {channel.mention}.",
            ephemeral=True,
        )

    @form_group.command(
        name="submissions",
        description="View recent submissions for a form.",
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(form=form_key_autocomplete)
    async def view_submissions(
        self,
        interaction: discord.Interaction,
        form: str,
        limit: int = 10,
    ) -> None:
        assert interaction.guild is not None

        form_store = get_form_store(self.bot)
        form_key = form.lower().strip()

        submissions = await form_store.list_submissions(
            guild_id=interaction.guild.id,
            form_key=form_key,
            limit=limit,
        )

        if not submissions:
            await interaction.response.send_message(
                f"No submissions found for `{form_key}`.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"Submissions: {form_key}",
            colour=discord.Colour.blurple(),
        )

        for submission in submissions:
            embed.add_field(
                name=submission.id,
                value=(
                    f"**User:** <@{submission.user_id}> (`{submission.user_id}`)\n"
                    f"**Submitted:** `{submission.submitted_at}`\n"
                    f"**Answers:** `{len(submission.answers)}`"
                ),
                inline=False,
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    bot.add_view(GenericFormStartView())
    await bot.add_cog(FormEditorCommand(bot))
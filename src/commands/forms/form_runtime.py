from __future__ import annotations

from dataclasses import dataclass, field
import uuid

import discord

from src.services.forms.constants import GENERIC_FORM_BUTTON_CUSTOM_ID
from src.services.forms.form_store import FormStore
from src.utils.form_builder import FormAnswer, build_form_modal


@dataclass
class GenericFormSession:
    user_id: int
    guild_id: int
    form_key: str
    answers: list[FormAnswer] = field(default_factory=list)


GENERIC_FORM_SESSIONS: dict[str, GenericFormSession] = {}


def get_form_store(client: discord.Client) -> FormStore | None:
    return getattr(client, "form_store", None)


async def build_generic_form_page_modal(
    client: discord.Client,
    guild_id: int,
    form_key: str,
    session_id: str,
    page_index: int,
) -> discord.ui.Modal:
    form_store = get_form_store(client)

    if form_store is None:
        raise RuntimeError("Form store is not available.")

    form = await form_store.get_form_config(
        guild_id=guild_id,
        form_key=form_key,
    )

    pages = form.pages()
    total_pages = len(pages)

    if total_pages == 0:
        raise ValueError("This form has no questions.")

    if page_index < 0 or page_index >= total_pages:
        raise ValueError(f"Invalid form page: {page_index}")

    page_questions = pages[page_index]

    page_suffix = f" {page_index + 1}/{total_pages}"
    max_base_title_length = 45 - len(page_suffix)
    title = f"{form.title[:max_base_title_length]}{page_suffix}"

    async def on_submit(
        interaction: discord.Interaction,
        answers: list[FormAnswer],
    ) -> None:
        await handle_generic_form_page_submit(
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


async def handle_generic_form_page_submit(
    interaction: discord.Interaction,
    session_id: str,
    page_index: int,
    answers: list[FormAnswer],
) -> None:
    session = GENERIC_FORM_SESSIONS.get(session_id)

    if session is None:
        await interaction.response.send_message(
            "This form session has expired. Please press the form button again.",
            ephemeral=True,
        )
        return

    if interaction.user.id != session.user_id:
        await interaction.response.send_message(
            "This is not your form session.",
            ephemeral=True,
        )
        return

    form_store = get_form_store(interaction.client)

    if form_store is None:
        await interaction.response.send_message(
            "Form storage is not available.",
            ephemeral=True,
        )
        return

    form = await form_store.get_form_config(
        guild_id=session.guild_id,
        form_key=session.form_key,
    )

    pages = form.pages()
    total_pages = len(pages)

    session.answers.extend(answers)

    next_page_index = page_index + 1

    if next_page_index < total_pages:
        await interaction.response.send_message(
            f"Page {page_index + 1}/{total_pages} saved. Continue to the next page.",
            view=ContinueGenericFormView(
                session_id=session_id,
                page_index=next_page_index,
            ),
            ephemeral=True,
        )
        return

    submission_id = uuid.uuid4().hex

    await form_store.save_submission(
        submission_id=submission_id,
        guild_id=session.guild_id,
        form_key=session.form_key,
        user_id=interaction.user.id,
        answers=session.answers,
    )

    del GENERIC_FORM_SESSIONS[session_id]

    await interaction.response.send_message(
        f"Your response has been submitted.\nSubmission ID: `{submission_id}`",
        ephemeral=True,
    )


class ContinueGenericFormView(discord.ui.View):
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
        custom_id="form:continue",
    )
    async def continue_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        session = GENERIC_FORM_SESSIONS.get(self.session_id)

        if session is None:
            await interaction.response.send_message(
                "This form session has expired. Please press the form button again.",
                ephemeral=True,
            )
            return

        if interaction.user.id != session.user_id:
            await interaction.response.send_message(
                "This is not your form session.",
                ephemeral=True,
            )
            return

        try:
            modal = await build_generic_form_page_modal(
                client=interaction.client,
                guild_id=session.guild_id,
                form_key=session.form_key,
                session_id=self.session_id,
                page_index=self.page_index,
            )

        except Exception as error:
            await interaction.response.send_message(
                f"Could not open the next form page: `{error}`",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(modal)


class GenericFormStartView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open Form",
        style=discord.ButtonStyle.primary,
        custom_id=GENERIC_FORM_BUTTON_CUSTOM_ID,
    )
    async def open_form_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild is None or interaction.message is None:
            await interaction.response.send_message(
                "This form can only be used inside a server.",
                ephemeral=True,
            )
            return

        form_store = get_form_store(interaction.client)

        if form_store is None:
            await interaction.response.send_message(
                "Form storage is not available.",
                ephemeral=True,
            )
            return

        published_form = await form_store.get_published_form_by_message(
            guild_id=interaction.guild.id,
            message_id=interaction.message.id,
        )

        if published_form is None:
            await interaction.response.send_message(
                "This form panel is no longer registered.",
                ephemeral=True,
            )
            return

        try:
            form = await form_store.get_form_config(
                guild_id=interaction.guild.id,
                form_key=published_form.form_key,
            )

            if not form.questions:
                await interaction.response.send_message(
                    "This form has no questions yet.",
                    ephemeral=True,
                )
                return

            session_id = uuid.uuid4().hex

            GENERIC_FORM_SESSIONS[session_id] = GenericFormSession(
                user_id=interaction.user.id,
                guild_id=interaction.guild.id,
                form_key=published_form.form_key,
            )

            modal = await build_generic_form_page_modal(
                client=interaction.client,
                guild_id=interaction.guild.id,
                form_key=published_form.form_key,
                session_id=session_id,
                page_index=0,
            )

        except Exception as error:
            await interaction.response.send_message(
                f"Could not open this form: `{error}`",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(modal)
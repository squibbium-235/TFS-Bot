from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

import discord


MAX_MODAL_TITLE_LENGTH = 45
MAX_CUSTOM_ID_LENGTH = 100
MAX_INPUT_LABEL_LENGTH = 45
MAX_PLACEHOLDER_LENGTH = 100
MAX_TEXT_INPUT_LENGTH = 4000
MAX_QUESTIONS_PER_MODAL = 5


@dataclass(frozen=True)
class FormQuestion:
    key: str
    label: str
    style: discord.TextStyle = discord.TextStyle.paragraph
    placeholder: str | None = None
    required: bool = True
    min_length: int | None = None
    max_length: int | None = None
    default: str | None = None


@dataclass(frozen=True)
class FormAnswer:
    key: str
    label: str
    value: str


FormSubmitCallback = Callable[
    [discord.Interaction, list[FormAnswer]],
    Awaitable[None],
]


class GeneratedFormModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        title: str,
        custom_id: str,
        questions: list[FormQuestion],
        on_submit_callback: FormSubmitCallback,
    ) -> None:
        validate_form(title, custom_id, questions)

        super().__init__(title=title, custom_id=custom_id)

        self.questions = questions
        self.on_submit_callback = on_submit_callback
        self.inputs_by_key: dict[str, discord.ui.TextInput] = {}

        for question in questions:
            text_input = discord.ui.TextInput(
                label=question.label,
                custom_id=question.key,
                style=question.style,
                placeholder=question.placeholder,
                required=question.required,
                min_length=question.min_length,
                max_length=question.max_length,
                default=question.default,
            )

            self.inputs_by_key[question.key] = text_input
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        answers = [
            FormAnswer(
                key=question.key,
                label=question.label,
                value=str(self.inputs_by_key[question.key].value).strip(),
            )
            for question in self.questions
        ]

        await self.on_submit_callback(interaction, answers)


def build_form_modal(
    *,
    title: str,
    custom_id: str,
    questions: list[FormQuestion],
    on_submit: FormSubmitCallback,
) -> GeneratedFormModal:
    return GeneratedFormModal(
        title=title,
        custom_id=custom_id,
        questions=questions,
        on_submit_callback=on_submit,
    )


def validate_form(
    title: str,
    custom_id: str,
    questions: list[FormQuestion],
) -> None:
    if not title.strip():
        raise ValueError("Modal title cannot be empty.")

    if len(title) > MAX_MODAL_TITLE_LENGTH:
        raise ValueError(f"Modal title cannot be longer than {MAX_MODAL_TITLE_LENGTH} characters.")

    if not custom_id.strip():
        raise ValueError("Modal custom_id cannot be empty.")

    if len(custom_id) > MAX_CUSTOM_ID_LENGTH:
        raise ValueError(f"Modal custom_id cannot be longer than {MAX_CUSTOM_ID_LENGTH} characters.")

    if not questions:
        raise ValueError("A modal must have at least one question.")

    if len(questions) > MAX_QUESTIONS_PER_MODAL:
        raise ValueError(f"Discord modals can only contain up to {MAX_QUESTIONS_PER_MODAL} questions.")

    seen_keys: set[str] = set()

    for question in questions:
        validate_question(question)

        if question.key in seen_keys:
            raise ValueError(f"Duplicate question key: {question.key}")

        seen_keys.add(question.key)


def validate_question(question: FormQuestion) -> None:
    if not question.key.strip():
        raise ValueError("Question key cannot be empty.")

    if len(question.key) > MAX_CUSTOM_ID_LENGTH:
        raise ValueError(f"Question key '{question.key}' is too long.")

    if not question.label.strip():
        raise ValueError(f"Question '{question.key}' must have a label.")

    if len(question.label) > MAX_INPUT_LABEL_LENGTH:
        raise ValueError(f"Question label '{question.label}' is too long.")

    if question.placeholder and len(question.placeholder) > MAX_PLACEHOLDER_LENGTH:
        raise ValueError(f"Placeholder for '{question.key}' is too long.")

    if question.min_length is not None and question.min_length < 0:
        raise ValueError(f"Question '{question.key}' cannot have negative min_length.")

    if question.max_length is not None and question.max_length > MAX_TEXT_INPUT_LENGTH:
        raise ValueError(f"Question '{question.key}' max_length cannot exceed {MAX_TEXT_INPUT_LENGTH}.")

    if (
        question.min_length is not None
        and question.max_length is not None
        and question.min_length > question.max_length
    ):
        raise ValueError(f"Question '{question.key}' has min_length greater than max_length.")

"""
Row shapes for a stored form and its questions.

These are the values the form editor reads back.
They are not the Discord modal objects; those are
built later from FormQuestion.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoredForm:
    """
    One form header: title, key, and the custom-id
    prefix used on its Discord components.
    """
    guild_id: int
    form_key: str
    title: str
    custom_id_prefix: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class StoredFormQuestion:
    """
    One question row, including its sort order.

    style is the stored text "short" or "paragraph",
    not a Discord TextStyle.
    """
    id: int
    guild_id: int
    form_key: str
    question_key: str
    label: str
    style: str
    required: bool
    placeholder: str | None
    min_length: int | None
    max_length: int | None
    sort_order: int
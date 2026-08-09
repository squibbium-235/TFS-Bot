from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoredForm:
    guild_id: int
    form_key: str
    title: str
    custom_id_prefix: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class StoredFormQuestion:
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
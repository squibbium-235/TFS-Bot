from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import discord

from src.utils.form_builder import FormQuestion

STYLE_MAP = {
    "short": discord.TextStyle.short,
    "paragraph": discord.TextStyle.paragraph
}

@dataclass(frozen=True)
class FormConfig:
    title: str
    custom_id_prefix: str
    questions: list[FormQuestion]

    def pages(self, page_size: int = 5) -> list[list[FormQuestion]]:
        return [
            self.questions[index:index + page_size]
            for index in range(0, len(self.questions), page_size)
        ]


class FormLoader:
    @staticmethod
    def load_form(path: str | Path) -> FormConfig:
        form_path = Path(path)

        if not form_path.exists():
            raise FileNotFoundError(f"Form config does not exist: {form_path}")
        
        with form_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        title = str(data["title"])
        custom_id_prefix = str(data["custom_id_prefix"])

        questions: list[FormQuestion] = []

        for item in data.get("questions", []):
            style_name = str(item.get("style", "paragraph")).lower()

            if style_name not in STYLE_MAP:
                raise ValueError(f"Invalid form question style '{style_name}'.\nUse 'short' or 'paragraph'.")
            
            questions.append(
                FormQuestion(
                    key=str(item["key"]),
                    label=str(item["label"]),
                    style=STYLE_MAP[style_name],
                    placeholder=item.get("placeholder"),
                    required=bool(item.get("required", True)),
                    min_length=item.get("min_length"),
                    max_length=item.get("max_length"),
                    default=item.get("default"),
                )
            )

        return FormConfig(
            title=title,
            custom_id_prefix=custom_id_prefix,
            questions=questions,
        )
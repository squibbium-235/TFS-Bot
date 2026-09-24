"""
Load a form definition from a JSON file.

Questions become FormQuestion objects. Only the
styles short and paragraph are accepted. A missing
style is paragraph, and a missing required flag
defaults to required.
"""

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
    """
    An in-memory form ready to show as Discord modals.
    """
    title: str
    custom_id_prefix: str
    questions: list[FormQuestion]

    def pages(self, page_size: int = 5) -> list[list[FormQuestion]]:
        """
        Split questions into modal pages.

        Discord allows at most five inputs on a modal,
        which is why the default page size is 5.
        """
        return [
            self.questions[index:index + page_size]
            for index in range(0, len(self.questions), page_size)
        ]


class FormLoader:
    """
    Read one form JSON file into a FormConfig.
    """
    @staticmethod
    def load_form(path: str | Path) -> FormConfig:
        """
        Load title, custom-id prefix, and questions.

        A missing file raises FileNotFoundError. An
        unknown style raises ValueError. Question
        length limits are not checked here.
        """
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
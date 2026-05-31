from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class GuildSettingsStore:
    def __init__(self, path: str = "data/guild_settings.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        if not self.path.exists():
            self._write_data({"guilds": {}})

    def get_review_channel_id(self, guild_id: int) -> int | None:
        data = self._read_data()
        guild_data = data.get("guilds", {}).get(str(guild_id), {})

        channel_id = guild_data.get("review_channel_id")

        return int(channel_id) if channel_id else None

    def set_review_channel_id(self, guild_id: int, channel_id: int) -> None:
        data = self._read_data()

        guilds = data.setdefault("guilds", {})
        guild_data = guilds.setdefault(str(guild_id), {})

        guild_data["review_channel_id"] = str(channel_id)

        self._write_data(data)

    def get_application_log_channel_id(self, guild_id: int) -> int | None:
        data = self._read_data()
        guild_data = data.get("guilds", {}).get(str(guild_id), {})

        channel_id = guild_data.get("application_log_channel_id")

        return int(channel_id) if channel_id else None

    def set_application_log_channel_id(
        self,
        guild_id: int,
        channel_id: int,
    ) -> None:
        data = self._read_data()

        guilds = data.setdefault("guilds", {})
        guild_data = guilds.setdefault(str(guild_id), {})

        guild_data["application_log_channel_id"] = str(channel_id)

        self._write_data(data)

    def _read_data(self) -> dict[str, Any]:
        with self.path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _write_data(self, data: dict[str, Any]) -> None:
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)
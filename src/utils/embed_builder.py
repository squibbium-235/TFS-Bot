from __future__ import annotations

import discord


class EmbedFactory:
    DEFAULT_FOOTER = "TFSBot"

    @staticmethod
    def base(
        title: str,
        description: str | None = None,
        colour: discord.Colour | None = None,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            colour=colour or discord.Colour.blurple(),
        )

        embed.set_footer(text=EmbedFactory.DEFAULT_FOOTER)
        return embed

    @staticmethod
    def success(message: str) -> discord.Embed:
        return EmbedFactory.base(
            title="Success",
            description=message,
            colour=discord.Colour.green(),
        )

    @staticmethod
    def warning(message: str) -> discord.Embed:
        return EmbedFactory.base(
            title="Warning",
            description=message,
            colour=discord.Colour.orange(),
        )

    @staticmethod
    def error(message: str) -> discord.Embed:
        return EmbedFactory.base(
            title="Error",
            description=message,
            colour=discord.Colour.red(),
        )

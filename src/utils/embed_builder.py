from __future__ import annotations

import discord


class EmbedFactory:
    DEFAULT_FOOTER = "TFSBot"

    MAX_FIELDS_PER_EMBED = 25
    MAX_EMBEDS_PER_MESSAGE = 10

    @staticmethod
    def base(
        title: str,
        description: str | None = None,
        colour: discord.Colour | None = None,
        image_url: str | None = None,
        thumbnail_url: str | None = None,
        author_name: str | None = None,
        author_icon_url: str | None = None,
        footer: str | None = DEFAULT_FOOTER,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=title[:256],
            description=description[:4096] if description else None,
            colour=colour or discord.Colour.blurple(),
        )

        if image_url:
            embed.set_image(url=image_url)

        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)

        if author_name:
            embed.set_author(
                name=author_name[:256],
                icon_url=author_icon_url if author_icon_url else None,
            )

        if footer:
            embed.set_footer(text=footer[:2048])

        return embed

    @staticmethod
    def from_hex_colour(hex_colour: str | None) -> discord.Colour:
        if not hex_colour:
            return discord.Colour.blurple()

        cleaned = hex_colour.strip().removeprefix("#")

        if len(cleaned) != 6:
            raise ValueError("Hex colour must be 6 characters, like #5865F2.")

        return discord.Colour(int(cleaned, 16))

    @staticmethod
    def from_web_form_embeds(
        title: str,
        description: str | None = None,
        hex_colour: str | None = None,
        image_url: str | None = None,
        thumbnail_url: str | None = None,
        author_name: str | None = None,
        author_icon_url: str | None = None,
        footer: str | None = DEFAULT_FOOTER,
        fields: list[tuple[str, str, bool]] | None = None,
    ) -> list[discord.Embed]:
        colour = EmbedFactory.from_hex_colour(hex_colour)

        clean_fields = [
            (name.strip(), value.strip(), inline)
            for name, value, inline in fields or []
            if name.strip() and value.strip()
        ]

        embeds: list[discord.Embed] = []

        first_embed = EmbedFactory.base(
            title=title,
            description=description,
            colour=colour,
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            author_name=author_name,
            author_icon_url=author_icon_url,
            footer=footer,
        )

        embeds.append(first_embed)

        current_embed = first_embed
        fields_on_current_embed = 0

        for field_name, field_value, inline in clean_fields:
            if fields_on_current_embed >= EmbedFactory.MAX_FIELDS_PER_EMBED:
                if len(embeds) >= EmbedFactory.MAX_EMBEDS_PER_MESSAGE:
                    break

                current_embed = EmbedFactory.base(
                    title=f"{title[:240]} Continued",
                    colour=colour,
                    footer=footer,
                )

                embeds.append(current_embed)
                fields_on_current_embed = 0

            current_embed.add_field(
                name=field_name[:256],
                value=field_value[:1024],
                inline=inline,
            )

            fields_on_current_embed += 1

        return embeds

    @staticmethod
    def from_web_form(
        title: str,
        description: str | None = None,
        hex_colour: str | None = None,
        image_url: str | None = None,
        thumbnail_url: str | None = None,
        author_name: str | None = None,
        author_icon_url: str | None = None,
        footer: str | None = DEFAULT_FOOTER,
        fields: list[tuple[str, str, bool]] | None = None,
    ) -> discord.Embed:
        return EmbedFactory.from_web_form_embeds(
            title=title,
            description=description,
            hex_colour=hex_colour,
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            author_name=author_name,
            author_icon_url=author_icon_url,
            footer=footer,
            fields=fields,
        )[0]

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
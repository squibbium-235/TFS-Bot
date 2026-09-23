from __future__ import annotations

from typing import Any

import discord

from src.services.welcome_store import (
    WelcomeSettings,
)


async def build_welcome_context(
    bot: discord.Client,
    guild: discord.Guild,
    member: discord.Member,
) -> dict[str, str]:
    inviter = "Unknown"

    invite_tracker = getattr(
        bot,
        "invite_tracker",
        None,
    )

    if invite_tracker is not None:
        try:
            invite_info = (
                await invite_tracker
                .get_member_invite_info(
                    guild_id=guild.id,
                    user_id=member.id,
                )
            )

            if invite_info is not None:
                if (
                    invite_info.inviter_id
                    is not None
                ):
                    inviter = (
                        f"<@{invite_info.inviter_id}>"
                    )
                elif invite_info.inviter_name:
                    inviter = str(
                        invite_info.inviter_name
                    )

        except Exception:
            inviter = "Unknown"

    return {
        "user": member.mention,
        "username": member.name,
        "display_name": (
            member.display_name
        ),
        "user_id": str(member.id),
        "server": guild.name,
        "member_count": str(
            guild.member_count
            if guild.member_count
            is not None
            else len(guild.members)
        ),
        "inviter": inviter,
        "avatar": (
            member.display_avatar.url
        ),
    }


def render_template_text(
    value: str,
    context: dict[str, str],
) -> str:
    rendered = value

    for key, replacement in (
        context.items()
    ):
        rendered = rendered.replace(
            "{" + key + "}",
            replacement,
        )

    return rendered


def render_template_value(
    value: Any,
    context: dict[str, str],
) -> Any:
    if isinstance(value, str):
        return render_template_text(
            value,
            context,
        )

    if isinstance(value, list):
        return [
            render_template_value(
                item,
                context,
            )
            for item in value
        ]

    if isinstance(value, dict):
        return {
            key: render_template_value(
                item,
                context,
            )
            for key, item in value.items()
        }

    return value


async def build_welcome_embed(
    bot: discord.Client,
    guild: discord.Guild,
    member: discord.Member,
    embed_data: dict[str, Any],
) -> discord.Embed:
    context = await build_welcome_context(
        bot=bot,
        guild=guild,
        member=member,
    )

    rendered_data = render_template_value(
        embed_data,
        context,
    )

    if not isinstance(
        rendered_data,
        dict,
    ):
        raise RuntimeError(
            "Welcome embed data is invalid."
        )

    embed = discord.Embed.from_dict(
        rendered_data
    )

    if not embed:
        raise RuntimeError(
            "Welcome embed is empty."
        )

    return embed


async def resolve_welcome_channel(
    bot: discord.Client,
    channel_id: int,
) -> discord.TextChannel:
    channel = bot.get_channel(
        channel_id
    )

    if channel is None:
        channel = await bot.fetch_channel(
            channel_id
        )

    if not isinstance(
        channel,
        discord.TextChannel,
    ):
        raise RuntimeError(
            "The configured welcome channel "
            "is not a text channel."
        )

    return channel


async def send_welcome_message(
    bot: discord.Client,
    settings: WelcomeSettings,
    member: discord.Member,
) -> discord.Message:
    if settings.channel_id is None:
        raise RuntimeError(
            "No welcome channel is configured."
        )

    channel = await resolve_welcome_channel(
        bot,
        settings.channel_id,
    )

    embed = await build_welcome_embed(
        bot=bot,
        guild=member.guild,
        member=member,
        embed_data=settings.embed_data,
    )

    return await channel.send(
        embed=embed,
        allowed_mentions=(
            discord.AllowedMentions.none()
        ),
    )
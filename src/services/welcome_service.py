from __future__ import annotations

import copy
from typing import Any

import discord

from src.services.welcome_store import (
    WelcomeSettings,
)
from src.webui.uploads import (
    WebUIUploadManager,
)


UPLOAD_SCHEME = "tfs-upload://"


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
                if invite_info.inviter_id is not None:
                    inviter = f"<@{invite_info.inviter_id}>"
                elif invite_info.inviter_name:
                    inviter = str(invite_info.inviter_name)

        except Exception:
            inviter = "Unknown"

    return {
        "user": member.mention,
        "username": member.name,
        "display_name": member.display_name,
        "user_id": str(member.id),
        "server": guild.name,
        "member_count": str(
            guild.member_count
            if guild.member_count is not None
            else len(guild.members)
        ),
        "inviter": inviter,
        "avatar": member.display_avatar.url,
    }


def render_template_text(
    value: str,
    context: dict[str, str],
) -> str:
    rendered = value

    for key, replacement in context.items():
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


def upload_value(reference: str) -> str:
    reference = reference.strip()

    if not reference:
        return ""

    return f"{UPLOAD_SCHEME}{reference}"


def upload_reference(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    if not value.startswith(UPLOAD_SCHEME):
        return None

    reference = value[len(UPLOAD_SCHEME):].strip()
    return reference or None


def _nested_url(
    data: dict[str, Any],
    key: str,
) -> str | None:
    section = data.get(key)

    if not isinstance(section, dict):
        return None

    value = section.get("url")

    if not isinstance(value, str):
        return None

    return value


def _author_icon_url(
    data: dict[str, Any],
) -> str | None:
    author = data.get("author")

    if not isinstance(author, dict):
        return None

    value = author.get("icon_url")

    if not isinstance(value, str):
        return None

    return value


def _remove_asset_url(
    data: dict[str, Any],
    key: str,
) -> None:
    section = data.get(key)

    if isinstance(section, dict):
        section.pop("url", None)

        if not section:
            data.pop(key, None)


def _remove_author_icon(
    data: dict[str, Any],
) -> None:
    author = data.get("author")

    if not isinstance(author, dict):
        return

    author.pop("icon_url", None)

    if not author:
        data.pop("author", None)


def _set_asset_url(
    data: dict[str, Any],
    key: str,
    url: str | None,
) -> None:
    if url is None:
        _remove_asset_url(
            data,
            key,
        )
        return

    section = data.get(key)

    if not isinstance(section, dict):
        section = {}
        data[key] = section

    section["url"] = url


def _set_author_icon(
    data: dict[str, Any],
    url: str | None,
) -> None:
    if url is None:
        _remove_author_icon(data)
        return

    author = data.get("author")

    if not isinstance(author, dict):
        author = {}
        data["author"] = author

    author["icon_url"] = url


async def _render_welcome_data(
    bot: discord.Client,
    guild: discord.Guild,
    member: discord.Member,
    embed_data: dict[str, Any],
) -> dict[str, Any]:
    context = await build_welcome_context(
        bot=bot,
        guild=guild,
        member=member,
    )

    rendered_data = render_template_value(
        copy.deepcopy(embed_data),
        context,
    )

    if not isinstance(rendered_data, dict):
        raise RuntimeError(
            "Welcome embed data is invalid."
        )

    return rendered_data


async def build_welcome_embed(
    bot: discord.Client,
    guild: discord.Guild,
    member: discord.Member,
    embed_data: dict[str, Any],
) -> discord.Embed:
    """
    Build an embed-only preview.

    Uploaded local images are omitted here because Discord requires the matching
    file attachments in the same message. Actual sends use
    build_welcome_message_payload(), which supplies both the embed and files.
    """
    rendered_data = await _render_welcome_data(
        bot=bot,
        guild=guild,
        member=member,
        embed_data=embed_data,
    )

    if upload_reference(
        _nested_url(rendered_data, "image")
    ):
        _remove_asset_url(
            rendered_data,
            "image",
        )

    if upload_reference(
        _nested_url(rendered_data, "thumbnail")
    ):
        _remove_asset_url(
            rendered_data,
            "thumbnail",
        )

    if upload_reference(
        _author_icon_url(rendered_data)
    ):
        _remove_author_icon(
            rendered_data
        )

    embed = discord.Embed.from_dict(
        rendered_data
    )

    if not embed:
        raise RuntimeError(
            "Welcome embed is empty."
        )

    return embed


async def build_welcome_message_payload(
    bot: discord.Client,
    guild: discord.Guild,
    member: discord.Member,
    embed_data: dict[str, Any],
) -> tuple[
    discord.Embed,
    list[discord.File],
]:
    rendered_data = await _render_welcome_data(
        bot=bot,
        guild=guild,
        member=member,
        embed_data=embed_data,
    )

    image_reference = upload_reference(
        _nested_url(
            rendered_data,
            "image",
        )
    )

    thumbnail_reference = upload_reference(
        _nested_url(
            rendered_data,
            "thumbnail",
        )
    )

    author_icon_reference = upload_reference(
        _author_icon_url(
            rendered_data
        )
    )

    upload_manager = WebUIUploadManager()

    (
        image_attachment_url,
        thumbnail_attachment_url,
        author_icon_attachment_url,
        files,
    ) = upload_manager.build_attachment_files(
        image_reference=image_reference,
        thumbnail_reference=thumbnail_reference,
        author_icon_reference=author_icon_reference,
    )

    if image_reference is not None:
        _set_asset_url(
            rendered_data,
            "image",
            image_attachment_url,
        )

    if thumbnail_reference is not None:
        _set_asset_url(
            rendered_data,
            "thumbnail",
            thumbnail_attachment_url,
        )

    if author_icon_reference is not None:
        _set_author_icon(
            rendered_data,
            author_icon_attachment_url,
        )

    embed = discord.Embed.from_dict(
        rendered_data
    )

    if not embed:
        upload_manager.close_files(files)
        raise RuntimeError(
            "Welcome embed is empty."
        )

    return embed, files


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

    embed, files = (
        await build_welcome_message_payload(
            bot=bot,
            guild=member.guild,
            member=member,
            embed_data=settings.embed_data,
        )
    )

    upload_manager = WebUIUploadManager()

    try:
        return await channel.send(
            embed=embed,
            files=(
                files
                if files
                else None
            ),
            allowed_mentions=(
                discord.AllowedMentions.none()
            ),
        )
    finally:
        upload_manager.close_files(
            files
        )

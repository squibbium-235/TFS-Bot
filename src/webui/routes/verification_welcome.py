from __future__ import annotations

from typing import Any

import discord

from flask import (
    Blueprint,
    render_template,
    request,
)

from src.services.welcome_service import (
    build_welcome_embed,
    send_welcome_message,
)
from src.services.welcome_store import (
    WelcomeSettings,
    WelcomeStore,
)
from src.webui.helpers import (
    require_owner,
    webui_context,
)


blueprint = Blueprint(
    "verification_welcome",
    __name__,
)


PLACEHOLDER_HELP = [
    ("{user}", "User mention"),
    ("{username}", "Discord username"),
    ("{display_name}", "Server display name"),
    ("{user_id}", "Discord user ID"),
    ("{server}", "Server name"),
    ("{member_count}", "Current member count"),
    ("{inviter}", "Tracked inviter"),
    ("{avatar}", "User avatar URL"),
]


def get_welcome_store(
) -> WelcomeStore:
    context = webui_context()

    store = getattr(
        context.bot,
        "welcome_store",
        None,
    )

    if isinstance(
        store,
        WelcomeStore,
    ):
        return store

    database_path = getattr(
        getattr(
            context.bot,
            "config",
            None,
        ),
        "application_db_path",
        "data/tfsbot.sqlite3",
    )

    store = WelcomeStore(
        database_path
    )

    context.run_coro(
        store.initialise()
    )

    setattr(
        context.bot,
        "welcome_store",
        store,
    )

    return store


def parse_colour(
    raw_value: str,
) -> int | None:
    cleaned = (
        raw_value
        .strip()
        .removeprefix("#")
        .removeprefix("0x")
    )

    if not cleaned:
        return None

    if (
        len(cleaned) != 6
        or any(
            character
            not in "0123456789abcdefABCDEF"
            for character in cleaned
        )
    ):
        raise ValueError(
            "Colour must be a 6-digit hex value, "
            "for example #5865F2."
        )

    return int(
        cleaned,
        16,
    )


def colour_text(
    embed_data: dict[str, Any],
) -> str:
    colour = embed_data.get(
        "color"
    )

    if not isinstance(
        colour,
        int,
    ):
        return "#5865F2"

    return f"#{colour:06X}"


def nested_value(
    embed_data: dict[str, Any],
    parent: str,
    child: str,
) -> str:
    parent_value = embed_data.get(
        parent
    )

    if not isinstance(
        parent_value,
        dict,
    ):
        return ""

    value = parent_value.get(
        child
    )

    return (
        str(value)
        if value is not None
        else ""
    )


def parse_embed_form(
) -> dict[str, Any]:
    embed_data: dict[
        str,
        Any,
    ] = {}

    title = request.form.get(
        "title",
        "",
    ).strip()

    description = request.form.get(
        "description",
        "",
    ).strip()

    colour = parse_colour(
        request.form.get(
            "colour",
            "",
        )
    )

    thumbnail_url = request.form.get(
        "thumbnail_url",
        "",
    ).strip()

    image_url = request.form.get(
        "image_url",
        "",
    ).strip()

    author_name = request.form.get(
        "author_name",
        "",
    ).strip()

    author_icon_url = request.form.get(
        "author_icon_url",
        "",
    ).strip()

    footer = request.form.get(
        "footer",
        "",
    ).strip()

    if title:
        embed_data["title"] = title

    if description:
        embed_data[
            "description"
        ] = description

    if colour is not None:
        embed_data[
            "color"
        ] = colour

    if thumbnail_url:
        embed_data[
            "thumbnail"
        ] = {
            "url": thumbnail_url,
        }

    if image_url:
        embed_data[
            "image"
        ] = {
            "url": image_url,
        }

    if author_name:
        author: dict[
            str,
            str,
        ] = {
            "name": author_name,
        }

        if author_icon_url:
            author[
                "icon_url"
            ] = author_icon_url

        embed_data[
            "author"
        ] = author

    if footer:
        embed_data[
            "footer"
        ] = {
            "text": footer,
        }

    field_ids = request.form.getlist(
        "field_id[]"
    )

    fields: list[
        dict[str, Any]
    ] = []

    for field_id in field_ids:
        field_name = request.form.get(
            f"field_{field_id}_name",
            "",
        ).strip()

        field_value = request.form.get(
            f"field_{field_id}_value",
            "",
        ).strip()

        inline = (
            request.form.get(
                f"field_{field_id}_inline"
            )
            == "on"
        )

        if (
            field_name
            and field_value
        ):
            fields.append(
                {
                    "name": (
                        field_name
                    ),
                    "value": (
                        field_value
                    ),
                    "inline": inline,
                }
            )

    if fields:
        embed_data[
            "fields"
        ] = fields

    if not embed_data:
        raise ValueError(
            "The welcome embed cannot be empty."
        )

    return embed_data


def template_values(
    settings: WelcomeSettings,
) -> dict[str, Any]:
    embed_data = (
        settings.embed_data
    )

    fields = embed_data.get(
        "fields",
        [],
    )

    if not isinstance(
        fields,
        list,
    ):
        fields = []

    return {
        "enabled": (
            settings.enabled
        ),
        "channel_id": (
            str(
                settings.channel_id
            )
            if settings.channel_id
            is not None
            else ""
        ),
        "title": str(
            embed_data.get(
                "title",
                "",
            )
            or ""
        ),
        "description": str(
            embed_data.get(
                "description",
                "",
            )
            or ""
        ),
        "colour": colour_text(
            embed_data
        ),
        "thumbnail_url": (
            nested_value(
                embed_data,
                "thumbnail",
                "url",
            )
        ),
        "image_url": (
            nested_value(
                embed_data,
                "image",
                "url",
            )
        ),
        "author_name": (
            nested_value(
                embed_data,
                "author",
                "name",
            )
        ),
        "author_icon_url": (
            nested_value(
                embed_data,
                "author",
                "icon_url",
            )
        ),
        "footer": (
            nested_value(
                embed_data,
                "footer",
                "text",
            )
        ),
        "fields": fields,
    }


async def resolve_test_member(
    guild: discord.Guild,
    user_id_text: str,
) -> discord.Member:
    cleaned = (
        user_id_text
        .strip()
        .replace("<@", "")
        .replace("!", "")
        .replace(">", "")
    )

    if not cleaned:
        raise ValueError(
            "Enter a user ID for the test."
        )

    try:
        user_id = int(
            cleaned
        )

    except ValueError as caught:
        raise ValueError(
            "Test user must be a Discord user ID."
        ) from caught

    member = guild.get_member(
        user_id
    )

    if member is not None:
        return member

    try:
        return await guild.fetch_member(
            user_id
        )

    except discord.HTTPException as caught:
        raise ValueError(
            "That user could not be found "
            "in the selected server."
        ) from caught


def render_page(
    *,
    guild: discord.Guild | None,
    settings: WelcomeSettings | None,
    message: str | None = None,
    error: str | None = None,
) -> str:
    context = webui_context()

    values = (
        template_values(
            settings
        )
        if settings is not None
        else {
            "enabled": False,
            "channel_id": "",
            "title": "",
            "description": "",
            "colour": "#5865F2",
            "thumbnail_url": "",
            "image_url": "",
            "author_name": "",
            "author_icon_url": "",
            "footer": "",
            "fields": [],
        }
    )

    return render_template(
        "verification/welcome.html",
        **context.template_context(
            title=(
                "TFSBot Welcome Message"
            ),
            active_page=(
                "verification"
            ),
            guilds=(
                context.available_guilds()
            ),
            selected_guild_id=(
                str(
                    guild.id
                )
                if guild
                else None
            ),
            text_channels=(
                context.guild_text_channels(
                    guild
                )
                if guild
                else []
            ),
            settings=settings,
            values=values,
            placeholders=(
                PLACEHOLDER_HELP
            ),
            message=message,
            error=error,
        ),
    )


@blueprint.route(
    "/verification/welcome",
    methods=[
        "GET",
        "POST",
    ],
)
def index():
    owner_error = require_owner()

    if owner_error is not None:
        return owner_error

    context = webui_context()

    guild_id_text = (
        request.form.get(
            "guild_id"
        )
        if request.method
        == "POST"
        else request.args.get(
            "guild_id"
        )
    )

    guild = (
        context.selected_guild(
            guild_id_text
        )
    )

    if guild is None:
        return render_page(
            guild=None,
            settings=None,
            error=(
                "No server is available."
            ),
        )

    store = get_welcome_store()

    try:
        settings = (
            context.run_coro(
                store.get_settings(
                    guild.id
                )
            )
        )

        if (
            request.method
            == "POST"
        ):
            action = (
                request.form.get(
                    "action",
                    "save",
                )
            )

            if action == "save":
                channel_id_text = (
                    request.form.get(
                        "channel_id",
                        "",
                    ).strip()
                )

                channel_id = (
                    int(
                        channel_id_text
                    )
                    if channel_id_text
                    else None
                )

                embed_data = (
                    parse_embed_form()
                )

                settings = (
                    context.run_coro(
                        store.save_config(
                            guild_id=(
                                guild.id
                            ),
                            channel_id=(
                                channel_id
                            ),
                            embed_data=(
                                embed_data
                            ),
                        )
                    )
                )

                context.audit(
                    action=(
                        "welcome.settings.save"
                    ),
                    guild_id=guild.id,
                    detail=(
                        "Updated verification "
                        "welcome message."
                    ),
                )

                return render_page(
                    guild=guild,
                    settings=settings,
                    message=(
                        "Welcome message saved."
                    ),
                )

            if action == "enable":
                if (
                    settings.channel_id
                    is None
                ):
                    raise ValueError(
                        "Choose and save a "
                        "welcome channel first."
                    )

                settings = (
                    context.run_coro(
                        store.set_enabled(
                            guild_id=(
                                guild.id
                            ),
                            enabled=True,
                        )
                    )
                )

                context.audit(
                    action=(
                        "welcome.enable"
                    ),
                    guild_id=guild.id,
                )

                return render_page(
                    guild=guild,
                    settings=settings,
                    message=(
                        "Welcome messages enabled."
                    ),
                )

            if action == "disable":
                settings = (
                    context.run_coro(
                        store.set_enabled(
                            guild_id=(
                                guild.id
                            ),
                            enabled=False,
                        )
                    )
                )

                context.audit(
                    action=(
                        "welcome.disable"
                    ),
                    guild_id=guild.id,
                )

                return render_page(
                    guild=guild,
                    settings=settings,
                    message=(
                        "Welcome messages disabled."
                    ),
                )

            if action == "test":
                test_member = (
                    context.run_coro(
                        resolve_test_member(
                            guild,
                            request.form.get(
                                "test_user_id",
                                "",
                            ),
                        )
                    )
                )

                if (
                    settings.channel_id
                    is None
                ):
                    raise ValueError(
                        "No welcome channel "
                        "is configured."
                    )

                message_result = (
                    context.run_coro(
                        send_welcome_message(
                            bot=context.bot,
                            settings=settings,
                            member=test_member,
                        )
                    )
                )

                context.audit(
                    action=(
                        "welcome.test"
                    ),
                    guild_id=guild.id,
                    detail=(
                        f"Test welcome sent "
                        f"for user "
                        f"{test_member.id}."
                    ),
                )

                return render_page(
                    guild=guild,
                    settings=settings,
                    message=(
                        "Test welcome sent: "
                        f"{message_result.jump_url}"
                    ),
                )

            if action == "preview":
                test_member = (
                    context.run_coro(
                        resolve_test_member(
                            guild,
                            request.form.get(
                                "test_user_id",
                                "",
                            ),
                        )
                    )
                )

                preview = (
                    context.run_coro(
                        build_welcome_embed(
                            bot=context.bot,
                            guild=guild,
                            member=(
                                test_member
                            ),
                            embed_data=(
                                parse_embed_form()
                            ),
                        )
                    )
                )

                return render_page(
                    guild=guild,
                    settings=settings,
                    message=(
                        "Preview generated in Discord "
                        "format. Browser preview is "
                        "shown below."
                    ),
                )

        return render_page(
            guild=guild,
            settings=settings,
        )

    except Exception as caught_error:
        settings = (
            context.run_coro(
                store.get_settings(
                    guild.id
                )
            )
        )

        return render_page(
            guild=guild,
            settings=settings,
            error=str(
                caught_error
            ),
        )
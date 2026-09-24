"""Owner editor for the post-approval welcome embed.

The nav stays on verification. Asset choice is a new upload, then a
typed URL, then a stored reference. Disable flips the stored flag and
does not save the form. Test sends the current form; preview only
builds the embed. A failed POST redisplays the stored settings.
"""

from __future__ import annotations

from dataclasses import replace
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
    upload_reference,
    upload_value,
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


def get_welcome_store() -> WelcomeStore:
    """Return the bot's welcome store, creating and initialising it if needed."""
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
    """Parse exactly six hex digits, or None when the field is empty.

    A leading # or 0x is removed. Anything else raises.
    """
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
            character not in "0123456789abcdefABCDEF"
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
    """Read the stored American ``color`` integer and render #RRGGBB.

    A missing or non-integer colour becomes the blurple default.
    """
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


def split_asset_value(
    value: str,
) -> tuple[str, str]:
    """Split a stored asset into an external URL or an upload reference.

    upload_reference recognises the upload marker. A plain URL is
    returned in the first position with an empty reference.
    """
    reference = upload_reference(
        value
    )

    if reference is not None:
        return "", reference

    return value, ""


def parse_uploaded_asset(
    *,
    guild: discord.Guild,
    upload_field: str,
    reference_field: str,
    url_field: str,
) -> str | None:
    """Resolve one image: new file, then typed URL, then stored upload.

    A typed URL intentionally beats a selected stored upload. New files
    are saved under welcome/<guild id> and wrapped with the upload marker.
    """
    context = webui_context()

    uploaded_file = request.files.get(
        upload_field
    )

    if (
        uploaded_file is not None
        and uploaded_file.filename
    ):
        reference = (
            context.uploads.save_upload(
                uploaded_file,
                folder=(
                    f"welcome/{guild.id}"
                ),
            )
        )

        return upload_value(
            reference
        )

    external_url = request.form.get(
        url_field,
        "",
    ).strip()

    # A typed URL intentionally wins over a selected stored upload.
    if external_url:
        return external_url

    selected_reference = request.form.get(
        reference_field,
        "",
    ).strip()

    if selected_reference:
        # validate_reference also prevents path traversal / malformed references.
        selected_reference = (
            context.uploads.validate_reference(
                selected_reference
            )
        )

        return upload_value(
            selected_reference
        )

    return None


def parse_embed_form(
    guild: discord.Guild,
) -> dict[str, Any]:
    """Build Discord embed JSON. Empty parts are omitted, and an empty embed raises.

    The colour is stored under ``color``. An author icon is kept only
    when an author name was posted, because the icon lives on that object.
    """
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

    thumbnail_url = parse_uploaded_asset(
        guild=guild,
        upload_field="thumbnail_upload",
        reference_field=(
            "thumbnail_upload_reference"
        ),
        url_field="thumbnail_url",
    )

    image_url = parse_uploaded_asset(
        guild=guild,
        upload_field="image_upload",
        reference_field=(
            "image_upload_reference"
        ),
        url_field="image_url",
    )

    author_name = request.form.get(
        "author_name",
        "",
    ).strip()

    author_icon_url = parse_uploaded_asset(
        guild=guild,
        upload_field="author_icon_upload",
        reference_field=(
            "author_icon_upload_reference"
        ),
        url_field="author_icon_url",
    )

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

        if field_name and field_value:
            fields.append(
                {
                    "name": field_name,
                    "value": field_value,
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


def parse_channel_id(
    guild: discord.Guild,
) -> int | None:
    raw_value = request.form.get(
        "channel_id",
        "",
    ).strip()

    if not raw_value:
        return None

    try:
        channel_id = int(
            raw_value
        )
    except ValueError as caught:
        raise ValueError(
            "Welcome channel is invalid."
        ) from caught

    channel = guild.get_channel(
        channel_id
    )

    if not isinstance(
        channel,
        discord.TextChannel,
    ):
        raise ValueError(
            "The selected welcome channel "
            "is not a text channel in this server."
        )

    return channel_id


def submitted_settings(
    *,
    guild: discord.Guild,
    existing: WelcomeSettings,
) -> WelcomeSettings:
    """Copy the form onto the existing settings without changing enabled.

    replace keeps the stored enabled flag until an enable or disable action.
    """
    return replace(
        existing,
        channel_id=parse_channel_id(
            guild
        ),
        embed_data=parse_embed_form(
            guild
        ),
    )


def template_values(
    settings: WelcomeSettings,
) -> dict[str, Any]:
    embed_data = settings.embed_data

    fields = embed_data.get(
        "fields",
        [],
    )

    if not isinstance(
        fields,
        list,
    ):
        fields = []

    thumbnail_url, thumbnail_upload_reference = (
        split_asset_value(
            nested_value(
                embed_data,
                "thumbnail",
                "url",
            )
        )
    )

    image_url, image_upload_reference = (
        split_asset_value(
            nested_value(
                embed_data,
                "image",
                "url",
            )
        )
    )

    author_icon_url, author_icon_upload_reference = (
        split_asset_value(
            nested_value(
                embed_data,
                "author",
                "icon_url",
            )
        )
    )

    return {
        "enabled": settings.enabled,
        "channel_id": (
            str(settings.channel_id)
            if settings.channel_id is not None
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
        "thumbnail_url": thumbnail_url,
        "thumbnail_upload_reference": (
            thumbnail_upload_reference
        ),
        "image_url": image_url,
        "image_upload_reference": (
            image_upload_reference
        ),
        "author_name": nested_value(
            embed_data,
            "author",
            "name",
        ),
        "author_icon_url": author_icon_url,
        "author_icon_upload_reference": (
            author_icon_upload_reference
        ),
        "footer": nested_value(
            embed_data,
            "footer",
            "text",
        ),
        "fields": fields,
    }


async def resolve_test_member(
    guild: discord.Guild,
    user_id_text: str,
) -> discord.Member:
    """Find a member from a raw id or a pasted mention.

    ``<@id>`` and ``<@!id>`` are stripped down to the digits. The cache
    is tried before a fetch.
    """
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
            "thumbnail_upload_reference": "",
            "image_url": "",
            "image_upload_reference": "",
            "author_name": "",
            "author_icon_url": "",
            "author_icon_upload_reference": "",
            "footer": "",
            "fields": [],
        }
    )

    return render_template(
        "verification/welcome.html",
        **context.template_context(
            title="TFSBot Welcome Message",
            active_page="verification",
            guilds=context.available_guilds(),
            selected_guild_id=(
                str(guild.id)
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
            uploaded_images=(
                context.uploads.list_images()
            ),
            settings=settings,
            values=values,
            placeholders=PLACEHOLDER_HELP,
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
    """Save, enable, disable, test, or validate the welcome embed.

    Enable writes the form and then turns the feature on, and it refuses
    a missing channel. Disable only clears the flag. Test posts the
    unsaved form. Preview builds the embed and does not send it. On any
    error the page reloads the stored settings, so the rejected form is
    not shown again.
    """
    owner_error = require_owner()

    if owner_error is not None:
        return owner_error

    context = webui_context()

    guild_id_text = (
        request.form.get(
            "guild_id"
        )
        if request.method == "POST"
        else request.args.get(
            "guild_id"
        )
    )

    guild = context.selected_guild(
        guild_id_text
    )

    if guild is None:
        return render_page(
            guild=None,
            settings=None,
            error="No server is available.",
        )

    store = get_welcome_store()

    try:
        settings = context.run_coro(
            store.get_settings(
                guild.id
            )
        )

        if request.method == "POST":
            action = request.form.get(
                "action",
                "save",
            )

            if action == "save":
                submitted = submitted_settings(
                    guild=guild,
                    existing=settings,
                )

                settings = context.run_coro(
                    store.save_config(
                        guild_id=guild.id,
                        channel_id=(
                            submitted.channel_id
                        ),
                        embed_data=(
                            submitted.embed_data
                        ),
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
                submitted = submitted_settings(
                    guild=guild,
                    existing=settings,
                )

                if submitted.channel_id is None:
                    raise ValueError(
                        "Choose a welcome channel "
                        "before enabling welcome messages."
                    )

                settings = context.run_coro(
                    store.save_config(
                        guild_id=guild.id,
                        channel_id=(
                            submitted.channel_id
                        ),
                        embed_data=(
                            submitted.embed_data
                        ),
                    )
                )

                settings = context.run_coro(
                    store.set_enabled(
                        guild_id=guild.id,
                        enabled=True,
                    )
                )

                context.audit(
                    action="welcome.enable",
                    guild_id=guild.id,
                    detail=(
                        "Saved current welcome "
                        "configuration and enabled it."
                    ),
                )

                return render_page(
                    guild=guild,
                    settings=settings,
                    message=(
                        "Welcome message saved "
                        "and enabled."
                    ),
                )

            # Does not write channel or embed changes from this POST.
            if action == "disable":
                settings = context.run_coro(
                    store.set_enabled(
                        guild_id=guild.id,
                        enabled=False,
                    )
                )

                context.audit(
                    action="welcome.disable",
                    guild_id=guild.id,
                )

                return render_page(
                    guild=guild,
                    settings=settings,
                    message=(
                        "Welcome messages disabled."
                    ),
                )

            # Uses the submitted form, which may not have been saved.
            if action == "test":
                test_member = context.run_coro(
                    resolve_test_member(
                        guild,
                        request.form.get(
                            "test_user_id",
                            "",
                        ),
                    )
                )

                test_settings = submitted_settings(
                    guild=guild,
                    existing=settings,
                )

                if test_settings.channel_id is None:
                    raise ValueError(
                        "Choose a welcome channel "
                        "before sending a test."
                    )

                message_result = context.run_coro(
                    send_welcome_message(
                        bot=context.bot,
                        settings=test_settings,
                        member=test_member,
                    )
                )

                context.audit(
                    action="welcome.test",
                    guild_id=guild.id,
                    detail=(
                        "Test welcome sent using "
                        "current form values for user "
                        f"{test_member.id}."
                    ),
                )

                return render_page(
                    guild=guild,
                    settings=test_settings,
                    message=(
                        "Test welcome sent using "
                        "the current form values: "
                        f"{message_result.jump_url}"
                    ),
                )

            # Validates the embed build and does not post a Discord message.
            if action == "preview":
                test_member = context.run_coro(
                    resolve_test_member(
                        guild,
                        request.form.get(
                            "test_user_id",
                            "",
                        ),
                    )
                )

                preview_settings = submitted_settings(
                    guild=guild,
                    existing=settings,
                )

                context.run_coro(
                    build_welcome_embed(
                        bot=context.bot,
                        guild=guild,
                        member=test_member,
                        embed_data=(
                            preview_settings.embed_data
                        ),
                    )
                )

                return render_page(
                    guild=guild,
                    settings=preview_settings,
                    message=(
                        "Preview validated using "
                        "the current form values."
                    ),
                )

        return render_page(
            guild=guild,
            settings=settings,
        )

    except Exception as caught_error:
        settings = context.run_coro(
            store.get_settings(
                guild.id
            )
        )

        return render_page(
            guild=guild,
            settings=settings,
            error=str(
                caught_error
            ),
        )

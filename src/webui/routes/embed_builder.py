from __future__ import annotations

from typing import Any

import discord

from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    url_for,
)

from src.services.saved_embed_store import (
    SavedEmbed,
    SavedEmbedStore,
)
from src.utils.embed_builder import (
    EmbedFactory,
)
from src.webui.helpers import (
    require_owner,
    webui_context,
)


blueprint = Blueprint(
    "embed_builder",
    __name__,
)


def get_saved_embed_store(
) -> SavedEmbedStore:
    context = webui_context()

    store = getattr(
        context.bot,
        "saved_embed_store",
        None,
    )

    if isinstance(
        store,
        SavedEmbedStore,
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

    store = SavedEmbedStore(
        database_path
    )

    context.run_coro(
        store.initialise()
    )

    setattr(
        context.bot,
        "saved_embed_store",
        store,
    )

    return store


def get_available_channels(
) -> list[dict[str, str]]:
    context = webui_context()

    channels: list[
        dict[str, str]
    ] = []

    for guild in context.bot.guilds:
        member = guild.me

        if member is None:
            continue

        for channel in guild.text_channels:
            permissions = (
                channel.permissions_for(
                    member
                )
            )

            if (
                not permissions.view_channel
                or not permissions.send_messages
            ):
                continue

            channels.append(
                {
                    "id": str(
                        channel.id
                    ),
                    "label": (
                        f"{guild.name} / "
                        f"#{channel.name}"
                    ),
                }
            )

    return channels


def parse_embed_form_payload(
) -> dict[str, Any]:
    field_ids = request.form.getlist(
        "field_id[]"
    )

    fields: list[
        dict[str, Any]
    ] = []

    for field_id in field_ids:
        name = request.form.get(
            f"field_{field_id}_name",
            "",
        ).strip()

        value = request.form.get(
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
            name
            and value
        ):
            fields.append(
                {
                    "name": name,
                    "value": value,
                    "inline": inline,
                }
            )

    return {
        "title": request.form.get(
            "title",
            "",
        ),
        "description": request.form.get(
            "description",
            "",
        ),
        "colour": request.form.get(
            "colour",
            "",
        ),
        "image_upload_filename": (
            request.form.get(
                "image_upload_filename"
            )
            or ""
        ),
        "image_url": request.form.get(
            "image_url",
            "",
        ),
        "thumbnail_upload_filename": (
            request.form.get(
                "thumbnail_upload_filename"
            )
            or ""
        ),
        "thumbnail_url": request.form.get(
            "thumbnail_url",
            "",
        ),
        "author_name": request.form.get(
            "author_name",
            "",
        ),
        "author_icon_upload_filename": (
            request.form.get(
                "author_icon_upload_filename"
            )
            or ""
        ),
        "author_icon_url": request.form.get(
            "author_icon_url",
            "",
        ),
        "footer": request.form.get(
            "footer",
            "",
        ),
        "fields": fields,
    }


def normalise_form_values(
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = payload or {}

    fields = payload.get(
        "fields",
        [],
    )

    if not isinstance(
        fields,
        list,
    ):
        fields = []

    return {
        "title": str(
            payload.get(
                "title",
                "",
            )
            or ""
        ),
        "description": str(
            payload.get(
                "description",
                "",
            )
            or ""
        ),
        "colour": str(
            payload.get(
                "colour",
                "#5865F2",
            )
            or "#5865F2"
        ),
        "image_upload_filename": str(
            payload.get(
                "image_upload_filename",
                "",
            )
            or ""
        ),
        "image_url": str(
            payload.get(
                "image_url",
                "",
            )
            or ""
        ),
        "thumbnail_upload_filename": str(
            payload.get(
                "thumbnail_upload_filename",
                "",
            )
            or ""
        ),
        "thumbnail_url": str(
            payload.get(
                "thumbnail_url",
                "",
            )
            or ""
        ),
        "author_name": str(
            payload.get(
                "author_name",
                "",
            )
            or ""
        ),
        "author_icon_upload_filename": str(
            payload.get(
                "author_icon_upload_filename",
                "",
            )
            or ""
        ),
        "author_icon_url": str(
            payload.get(
                "author_icon_url",
                "",
            )
            or ""
        ),
        "footer": str(
            payload.get(
                "footer",
                "TFSBot",
            )
            or ""
        ),
        "fields": fields,
    }


async def send_embeds_to_channel(
    bot: discord.Client,
    channel_id: int,
    embeds: list[discord.Embed],
    files: list[discord.File],
) -> None:
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
            "Selected channel is "
            "not a text channel."
        )

    await channel.send(
        embeds=embeds,
        files=(
            files
            if files
            else None
        ),
    )


def build_embeds_from_payload(
    payload: dict[str, Any],
) -> tuple[
    list[discord.Embed],
    list[discord.File],
]:
    context = webui_context()

    raw_fields = payload.get(
        "fields",
        [],
    )

    fields: list[
        tuple[
            str,
            str,
            bool,
        ]
    ] = []

    if isinstance(
        raw_fields,
        list,
    ):
        for raw_field in raw_fields:
            if not isinstance(
                raw_field,
                dict,
            ):
                continue

            name = str(
                raw_field.get(
                    "name",
                    "",
                )
            ).strip()

            value = str(
                raw_field.get(
                    "value",
                    "",
                )
            ).strip()

            inline = bool(
                raw_field.get(
                    "inline",
                    False,
                )
            )

            if (
                name
                and value
            ):
                fields.append(
                    (
                        name,
                        value,
                        inline,
                    )
                )

    (
        image_attachment_url,
        thumbnail_attachment_url,
        author_icon_attachment_url,
        files,
    ) = (
        context.uploads
        .build_attachment_files(
            image_reference=(
                str(
                    payload.get(
                        "image_upload_filename",
                        "",
                    )
                ).strip()
                or None
            ),
            thumbnail_reference=(
                str(
                    payload.get(
                        "thumbnail_upload_filename",
                        "",
                    )
                ).strip()
                or None
            ),
            author_icon_reference=(
                str(
                    payload.get(
                        "author_icon_upload_filename",
                        "",
                    )
                ).strip()
                or None
            ),
        )
    )

    image_url = (
        image_attachment_url
        or str(
            payload.get(
                "image_url",
                "",
            )
        ).strip()
        or None
    )

    thumbnail_url = (
        thumbnail_attachment_url
        or str(
            payload.get(
                "thumbnail_url",
                "",
            )
        ).strip()
        or None
    )

    author_icon_url = (
        author_icon_attachment_url
        or str(
            payload.get(
                "author_icon_url",
                "",
            )
        ).strip()
        or None
    )

    embeds = (
        EmbedFactory
        .from_web_form_embeds(
            title=str(
                payload.get(
                    "title",
                    "",
                )
            ),
            description=(
                str(
                    payload.get(
                        "description",
                        "",
                    )
                )
                or None
            ),
            hex_colour=(
                str(
                    payload.get(
                        "colour",
                        "",
                    )
                )
                or None
            ),
            image_url=image_url,
            thumbnail_url=(
                thumbnail_url
            ),
            author_name=(
                str(
                    payload.get(
                        "author_name",
                        "",
                    )
                )
                or None
            ),
            author_icon_url=(
                author_icon_url
            ),
            footer=(
                str(
                    payload.get(
                        "footer",
                        "",
                    )
                )
                or None
            ),
            fields=fields,
        )
    )

    return embeds, files


def render_page(
    *,
    message: str | None = None,
    error: str | None = None,
    loaded_embed: SavedEmbed | None = None,
    form_payload: dict[str, Any] | None = None,
) -> str:
    context = webui_context()

    store = get_saved_embed_store()

    saved_embeds = context.run_coro(
        store.list_embeds()
    )

    if (
        form_payload is None
        and loaded_embed is not None
    ):
        form_payload = (
            loaded_embed.payload
        )

    form_values = normalise_form_values(
        form_payload
    )

    return render_template(
        "embed_builder/index.html",
        **context.template_context(
            title=(
                "TFSBot Embed Builder"
            ),
            active_page="embed_builder",
            channels=(
                get_available_channels()
            ),
            uploaded_images=(
                context.uploads
                .list_images()
            ),
            upload_folders=(
                context.uploads
                .list_folders()
            ),
            saved_embeds=saved_embeds,
            loaded_embed=loaded_embed,
            form_values=form_values,
            message=message,
            error=error,
        ),
    )


@blueprint.route(
    "/embed-builder"
)
def index():
    owner_error = require_owner()

    if owner_error is not None:
        return owner_error

    saved_embed_id_text = (
        request.args.get(
            "saved_id",
            "",
        ).strip()
    )

    if not saved_embed_id_text:
        return render_page()

    try:
        saved_embed_id = int(
            saved_embed_id_text
        )

    except ValueError:
        return render_page(
            error=(
                "Saved embed ID is invalid."
            ),
        )

    context = webui_context()

    saved_embed = context.run_coro(
        get_saved_embed_store()
        .get_embed(
            saved_embed_id
        )
    )

    if saved_embed is None:
        return render_page(
            error=(
                "That saved embed "
                "no longer exists."
            ),
        )

    return render_page(
        loaded_embed=saved_embed
    )


@blueprint.route(
    "/embed-builder/upload",
    methods=[
        "POST",
    ],
)
def upload_image():
    owner_error = require_owner()

    if owner_error is not None:
        return owner_error

    context = webui_context()

    try:
        folder = (
            request.form.get(
                "new_folder"
            )
            or request.form.get(
                "folder"
            )
            or ""
        )

        reference = (
            context.uploads
            .save_upload(
                request.files.get(
                    "image"
                ),
                folder,
            )
        )

        return render_page(
            message=(
                f"Uploaded "
                f"{reference}."
            ),
        )

    except Exception as caught_error:
        return render_page(
            error=str(
                caught_error
            ),
        )


@blueprint.route(
    "/embed-builder/save",
    methods=[
        "POST",
    ],
)
def save_embed():
    owner_error = require_owner()

    if owner_error is not None:
        return owner_error

    context = webui_context()

    payload = (
        parse_embed_form_payload()
    )

    try:
        saved_embed = context.run_coro(
            get_saved_embed_store()
            .create_embed(
                name=request.form.get(
                    "saved_name",
                    "",
                ),
                payload=payload,
            )
        )

        return render_page(
            message=(
                f"Saved embed "
                f"“{saved_embed.name}”."
            ),
            loaded_embed=saved_embed,
        )

    except Exception as caught_error:
        return render_page(
            error=str(
                caught_error
            ),
            form_payload=payload,
        )


@blueprint.route(
    "/embed-builder/update",
    methods=[
        "POST",
    ],
)
def update_embed():
    owner_error = require_owner()

    if owner_error is not None:
        return owner_error

    context = webui_context()

    payload = (
        parse_embed_form_payload()
    )

    try:
        saved_embed_id = int(
            request.form[
                "saved_id"
            ]
        )

        saved_embed = context.run_coro(
            get_saved_embed_store()
            .update_embed(
                saved_embed_id=(
                    saved_embed_id
                ),
                name=request.form.get(
                    "saved_name",
                    "",
                ),
                payload=payload,
            )
        )

        return render_page(
            message=(
                f"Updated embed "
                f"“{saved_embed.name}”."
            ),
            loaded_embed=saved_embed,
        )

    except Exception as caught_error:
        return render_page(
            error=str(
                caught_error
            ),
            form_payload=payload,
        )


@blueprint.route(
    "/embed-builder/delete",
    methods=[
        "POST",
    ],
)
def delete_embed():
    owner_error = require_owner()

    if owner_error is not None:
        return owner_error

    context = webui_context()

    try:
        saved_embed_id = int(
            request.form[
                "saved_id"
            ]
        )

        deleted = context.run_coro(
            get_saved_embed_store()
            .delete_embed(
                saved_embed_id
            )
        )

        if not deleted:
            raise RuntimeError(
                "That saved embed "
                "no longer exists."
            )

        return redirect(
            url_for(
                "embed_builder.index"
            )
        )

    except Exception as caught_error:
        return render_page(
            error=str(
                caught_error
            ),
        )


@blueprint.route(
    "/embed-builder/send",
    methods=[
        "POST",
    ],
)
def send_embed():
    owner_error = require_owner()

    if owner_error is not None:
        return owner_error

    context = webui_context()

    payload = (
        parse_embed_form_payload()
    )

    files: list[
        discord.File
    ] = []

    try:
        channel_id = int(
            request.form[
                "channel_id"
            ]
        )

        (
            embeds,
            files,
        ) = build_embeds_from_payload(
            payload
        )

        context.run_coro(
            send_embeds_to_channel(
                bot=context.bot,
                channel_id=channel_id,
                embeds=embeds,
                files=files,
            )
        )

        loaded_embed = None

        saved_embed_id_text = (
            request.form.get(
                "saved_id",
                "",
            ).strip()
        )

        if saved_embed_id_text:
            try:
                loaded_embed = (
                    context.run_coro(
                        get_saved_embed_store()
                        .get_embed(
                            int(
                                saved_embed_id_text
                            )
                        )
                    )
                )

            except ValueError:
                loaded_embed = None

        return render_page(
            message=(
                "Embed sent. Used "
                f"{len(embeds)} embed(s)."
            ),
            loaded_embed=loaded_embed,
            form_payload=payload,
        )

    except Exception as caught_error:
        return render_page(
            error=str(
                caught_error
            ),
            form_payload=payload,
        )

    finally:
        context.uploads.close_files(
            files
        )
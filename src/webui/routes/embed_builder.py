from __future__ import annotations

import discord

from flask import (
    Blueprint,
    render_template,
    request,
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


def render_page(
    *,
    message: str | None = None,
    error: str | None = None,
) -> str:
    context = webui_context()

    return render_template(
        "embed_builder/index.html",
        **context.template_context(
            title="TFSBot Embed Builder",
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

    return render_page()


@blueprint.route(
    "/embed-builder/upload",
    methods=["POST"],
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
    "/embed-builder/send",
    methods=["POST"],
)
def send_embed():
    owner_error = require_owner()

    if owner_error is not None:
        return owner_error

    context = webui_context()

    files: list[
        discord.File
    ] = []

    try:
        channel_id = int(
            request.form[
                "channel_id"
            ]
        )

        field_ids = (
            request.form.getlist(
                "field_id[]"
            )
        )

        fields: list[
            tuple[
                str,
                str,
                bool,
            ]
        ] = []

        for field_id in field_ids:
            name = request.form.get(
                f"field_{field_id}_name",
                "",
            )

            value = request.form.get(
                f"field_{field_id}_value",
                "",
            )

            inline = (
                request.form.get(
                    f"field_{field_id}_inline"
                )
                == "on"
            )

            if (
                name.strip()
                and value.strip()
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
                    request.form.get(
                        "image_upload_filename"
                    )
                    or None
                ),
                thumbnail_reference=(
                    request.form.get(
                        "thumbnail_upload_filename"
                    )
                    or None
                ),
                author_icon_reference=(
                    request.form.get(
                        "author_icon_upload_filename"
                    )
                    or None
                ),
            )
        )

        image_url = (
            image_attachment_url
            or request.form.get(
                "image_url"
            )
            or None
        )

        thumbnail_url = (
            thumbnail_attachment_url
            or request.form.get(
                "thumbnail_url"
            )
            or None
        )

        author_icon_url = (
            author_icon_attachment_url
            or request.form.get(
                "author_icon_url"
            )
            or None
        )

        embeds = (
            EmbedFactory
            .from_web_form_embeds(
                title=request.form.get(
                    "title",
                    "",
                ),
                description=(
                    request.form.get(
                        "description"
                    )
                    or None
                ),
                hex_colour=(
                    request.form.get(
                        "colour"
                    )
                    or None
                ),
                image_url=image_url,
                thumbnail_url=(
                    thumbnail_url
                ),
                author_name=(
                    request.form.get(
                        "author_name"
                    )
                    or None
                ),
                author_icon_url=(
                    author_icon_url
                ),
                footer=(
                    request.form.get(
                        "footer"
                    )
                    or None
                ),
                fields=fields,
            )
        )

        context.run_coro(
            send_embeds_to_channel(
                bot=context.bot,
                channel_id=channel_id,
                embeds=embeds,
                files=files,
            )
        )

        return render_page(
            message=(
                "Embed sent. Used "
                f"{len(embeds)} embed(s)."
            ),
        )

    except Exception as caught_error:
        return render_page(
            error=str(
                caught_error
            ),
        )

    finally:
        context.uploads.close_files(
            files
        )
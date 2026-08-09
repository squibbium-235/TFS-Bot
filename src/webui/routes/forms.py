from __future__ import annotations

from typing import Any

import discord

from flask import (
    Blueprint,
    render_template,
    request,
)

from src.commands.forms.form_runtime import (
    GenericFormStartView,
)
from src.services.forms.constants import (
    FORM_KEY_VERIFICATION,
    VERIFICATION_FORM_PATH,
)
from src.webui.helpers import (
    require_owner,
    webui_context,
)


blueprint = Blueprint(
    "forms",
    __name__,
)


def clean_form_key(
    raw_value: str,
) -> str:
    return raw_value.lower().strip()


def parse_optional_int(
    raw_value: str | None,
) -> int | None:
    if raw_value is None:
        return None

    stripped = raw_value.strip()

    if not stripped:
        return None

    return int(stripped)


async def get_guild_forms(
    guild: discord.Guild,
) -> list[dict[str, str]]:
    context = webui_context()

    form_store = (
        context.form_store()
    )

    stored_forms = (
        await form_store.list_forms(
            guild.id
        )
    )

    forms = [
        {
            "key": form.form_key,
            "title": form.title,
        }
        for form in stored_forms
    ]

    if not any(
        form["key"]
        == FORM_KEY_VERIFICATION
        for form in forms
    ):
        forms.insert(
            0,
            {
                "key": FORM_KEY_VERIFICATION,
                "title": "Verification",
            },
        )

    return forms


@blueprint.route(
    "/forms",
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

    message: str | None = None
    error: str | None = None

    selected_guild = (
        context.selected_guild(
            request.form.get(
                "guild_id"
            )
            if request.method == "POST"
            else request.args.get(
                "guild_id"
            )
        )
    )

    selected_form_key = (
        clean_form_key(
            request.form.get(
                "form_key",
                "",
            )
            if request.method == "POST"
            else request.args.get(
                "form_key",
                "",
            )
        )
    )

    try:
        form_store = (
            context.form_store()
        )

        settings_store = (
            context.guild_settings_store()
        )

        if request.method == "POST":
            if selected_guild is None:
                raise RuntimeError(
                    "No server selected."
                )

            action = request.form.get(
                "action",
                "",
            )

            if action == "create_form":
                new_form_key = (
                    clean_form_key(
                        request.form.get(
                            "new_form_key",
                            "",
                        )
                    )
                )

                new_title = (
                    request.form.get(
                        "new_form_title",
                        "",
                    ).strip()
                )

                new_prefix = (
                    request.form.get(
                        "new_custom_id_prefix",
                        "",
                    ).strip()
                    or None
                )

                context.run_coro(
                    form_store.create_form(
                        guild_id=(
                            selected_guild.id
                        ),
                        form_key=(
                            new_form_key
                        ),
                        title=new_title,
                        custom_id_prefix=(
                            new_prefix
                        ),
                    )
                )

                selected_form_key = (
                    new_form_key
                )

                message = (
                    f"Created form "
                    f"`{new_form_key}`."
                )

            elif action == "save_form":
                if not selected_form_key:
                    raise RuntimeError(
                        "No form selected."
                    )

                updated = context.run_coro(
                    form_store.update_form(
                        guild_id=(
                            selected_guild.id
                        ),
                        form_key=(
                            selected_form_key
                        ),
                        title=request.form.get(
                            "form_title",
                            "",
                        ),
                        custom_id_prefix=(
                            request.form.get(
                                "custom_id_prefix",
                                "",
                            )
                        ),
                    )
                )

                if not updated:
                    raise RuntimeError(
                        "Form was not found."
                    )

                message = (
                    f"Saved form "
                    f"`{selected_form_key}`."
                )

            elif (
                action
                == "set_verification_form"
            ):
                if not selected_form_key:
                    raise RuntimeError(
                        "No form selected."
                    )

                context.run_coro(
                    form_store.get_form_config(
                        guild_id=(
                            selected_guild.id
                        ),
                        form_key=(
                            selected_form_key
                        ),
                        fallback_json_path=(
                            VERIFICATION_FORM_PATH
                        ),
                    )
                )

                settings_store.set_verification_form_key(
                    selected_guild.id,
                    selected_form_key,
                )

                message = (
                    "Verification form changed "
                    f"to `{selected_form_key}`. "
                    "Repost the verification "
                    "panel if needed."
                )

            elif (
                action
                == "reset_verification_form"
            ):
                if (
                    request.form.get(
                        "reset_confirm",
                        "",
                    ).strip()
                    != "RESET"
                ):
                    raise RuntimeError(
                        "Type RESET to reset "
                        "the built-in "
                        "verification form."
                    )

                context.run_coro(
                    form_store
                    .reset_verification_form_from_json(
                        guild_id=(
                            selected_guild.id
                        ),
                        json_path=(
                            VERIFICATION_FORM_PATH
                        ),
                    )
                )

                selected_form_key = (
                    FORM_KEY_VERIFICATION
                )

                message = (
                    "Built-in verification "
                    "form reset."
                )

            elif action == "add_question":
                if not selected_form_key:
                    raise RuntimeError(
                        "No form selected."
                    )

                context.run_coro(
                    form_store.add_question(
                        guild_id=(
                            selected_guild.id
                        ),
                        form_key=(
                            selected_form_key
                        ),
                        question_key=(
                            clean_form_key(
                                request.form.get(
                                    "question_key",
                                    "",
                                )
                            )
                        ),
                        label=(
                            request.form.get(
                                "question_label",
                                "",
                            ).strip()
                        ),
                        style=(
                            request.form.get(
                                "question_style",
                                "paragraph",
                            )
                        ),
                        required=(
                            request.form.get(
                                "question_required"
                            )
                            == "on"
                        ),
                        placeholder=(
                            request.form.get(
                                "question_placeholder",
                                "",
                            ).strip()
                            or None
                        ),
                        min_length=(
                            parse_optional_int(
                                request.form.get(
                                    "question_min_length"
                                )
                            )
                        ),
                        max_length=(
                            parse_optional_int(
                                request.form.get(
                                    "question_max_length"
                                )
                            )
                        ),
                        fallback_json_path=(
                            VERIFICATION_FORM_PATH
                        ),
                    )
                )

                message = "Question added."

            elif action == "save_questions":
                if not selected_form_key:
                    raise RuntimeError(
                        "No form selected."
                    )

                ordered_keys: list[
                    tuple[int, str]
                ] = []

                for question_key in (
                    request.form.getlist(
                        "question_key[]"
                    )
                ):
                    question_key = (
                        clean_form_key(
                            question_key
                        )
                    )

                    context.run_coro(
                        form_store
                        .update_question(
                            guild_id=(
                                selected_guild.id
                            ),
                            form_key=(
                                selected_form_key
                            ),
                            question_key=(
                                question_key
                            ),
                            label=(
                                request.form.get(
                                    f"label_{question_key}",
                                    "",
                                ).strip()
                            ),
                            style=(
                                request.form.get(
                                    f"style_{question_key}",
                                    "paragraph",
                                )
                            ),
                            required=(
                                request.form.get(
                                    f"required_{question_key}"
                                )
                                == "on"
                            ),
                            placeholder=(
                                request.form.get(
                                    f"placeholder_{question_key}",
                                    "",
                                ).strip()
                                or None
                            ),
                            min_length=(
                                parse_optional_int(
                                    request.form.get(
                                        f"min_length_{question_key}"
                                    )
                                )
                            ),
                            max_length=(
                                parse_optional_int(
                                    request.form.get(
                                        f"max_length_{question_key}"
                                    )
                                )
                            ),
                            clear_placeholder=True,
                            clear_lengths=True,
                            fallback_json_path=(
                                VERIFICATION_FORM_PATH
                            ),
                        )
                    )

                    ordered_keys.append(
                        (
                            parse_optional_int(
                                request.form.get(
                                    f"sort_order_{question_key}"
                                )
                            )
                            or 9999,
                            question_key,
                        )
                    )

                context.run_coro(
                    form_store
                    .set_question_order(
                        guild_id=(
                            selected_guild.id
                        ),
                        form_key=(
                            selected_form_key
                        ),
                        question_keys=[
                            question_key
                            for (
                                _,
                                question_key,
                            )
                            in sorted(
                                ordered_keys
                            )
                        ],
                    )
                )

                message = (
                    "Question changes saved."
                )

            elif action == "delete_question":
                if (
                    request.form.get(
                        "delete_question_confirm",
                        "",
                    ).strip()
                    != "DELETE"
                ):
                    raise RuntimeError(
                        "Type DELETE to "
                        "delete the question."
                    )

                question_key = (
                    clean_form_key(
                        request.form.get(
                            "delete_question_key",
                            "",
                        )
                    )
                )

                deleted = context.run_coro(
                    form_store.delete_question(
                        guild_id=(
                            selected_guild.id
                        ),
                        form_key=(
                            selected_form_key
                        ),
                        question_key=(
                            question_key
                        ),
                        fallback_json_path=(
                            VERIFICATION_FORM_PATH
                        ),
                    )
                )

                if not deleted:
                    raise RuntimeError(
                        "Question was not found."
                    )

                message = (
                    f"Deleted question "
                    f"`{question_key}`."
                )

            elif action == "publish_form":
                if not selected_form_key:
                    raise RuntimeError(
                        "No form selected."
                    )

                channel_id = int(
                    request.form.get(
                        "publish_channel_id",
                        "0",
                    )
                )

                channel = (
                    selected_guild.get_channel(
                        channel_id
                    )
                )

                if channel is None:
                    channel = context.run_coro(
                        context.bot.fetch_channel(
                            channel_id
                        )
                    )

                if not isinstance(
                    channel,
                    discord.TextChannel,
                ):
                    raise RuntimeError(
                        "Selected channel is "
                        "not a text channel."
                    )

                form_config = (
                    context.run_coro(
                        form_store
                        .get_form_config(
                            guild_id=(
                                selected_guild.id
                            ),
                            form_key=(
                                selected_form_key
                            ),
                            fallback_json_path=(
                                VERIFICATION_FORM_PATH
                            ),
                        )
                    )
                )

                if not form_config.questions:
                    raise RuntimeError(
                        "Add at least one "
                        "question before "
                        "publishing this form."
                    )

                publish_title = (
                    request.form.get(
                        "publish_title",
                        "",
                    ).strip()
                )

                publish_description = (
                    request.form.get(
                        "publish_description",
                        "",
                    ).strip()
                )

                if (
                    not publish_title
                    or not publish_description
                ):
                    raise RuntimeError(
                        "Publish title and "
                        "description are required."
                    )

                (
                    image_attachment_url,
                    thumbnail_attachment_url,
                    _,
                    files,
                ) = (
                    context.uploads
                    .build_attachment_files(
                        image_reference=(
                            request.form.get(
                                "publish_image_upload_filename"
                            )
                            or None
                        ),
                        thumbnail_reference=(
                            request.form.get(
                                "publish_thumbnail_upload_filename"
                            )
                            or None
                        ),
                    )
                )

                embed = discord.Embed(
                    title=publish_title,
                    description=(
                        publish_description
                    ),
                    colour=(
                        discord.Colour
                        .blurple()
                    ),
                )

                if thumbnail_attachment_url:
                    embed.set_thumbnail(
                        url=(
                            thumbnail_attachment_url
                        )
                    )

                elif (
                    selected_guild.icon
                    is not None
                ):
                    embed.set_thumbnail(
                        url=(
                            selected_guild
                            .icon
                            .url
                        )
                    )

                if image_attachment_url:
                    embed.set_image(
                        url=image_attachment_url
                    )

                embed.set_footer(
                    text=(
                        f"Form: "
                        f"{form_config.title}"
                    )
                )

                try:
                    message_object = (
                        context.run_coro(
                            channel.send(
                                embed=embed,
                                view=(
                                    GenericFormStartView()
                                ),
                                files=(
                                    files
                                    if files
                                    else None
                                ),
                            )
                        )
                    )

                finally:
                    context.uploads.close_files(
                        files
                    )

                context.run_coro(
                    form_store
                    .save_published_form(
                        guild_id=(
                            selected_guild.id
                        ),
                        form_key=(
                            selected_form_key
                        ),
                        channel_id=(
                            channel.id
                        ),
                        message_id=(
                            message_object.id
                        ),
                        title=(
                            publish_title
                        ),
                        description=(
                            publish_description
                        ),
                    )
                )

                message = (
                    "Published form "
                    f"`{selected_form_key}` "
                    f"in #{channel.name}."
                )

            elif action == "delete_form":
                if (
                    request.form.get(
                        "delete_form_confirm",
                        "",
                    ).strip()
                    != "DELETE"
                ):
                    raise RuntimeError(
                        "Type DELETE to "
                        "delete the form."
                    )

                verification_form_key = (
                    settings_store
                    .get_verification_form_key(
                        selected_guild.id
                    )
                    or FORM_KEY_VERIFICATION
                )

                if (
                    selected_form_key
                    == verification_form_key
                ):
                    raise RuntimeError(
                        "Choose another "
                        "verification form "
                        "before deleting this one."
                    )

                deleted = context.run_coro(
                    form_store.delete_form(
                        guild_id=(
                            selected_guild.id
                        ),
                        form_key=(
                            selected_form_key
                        ),
                    )
                )

                if not deleted:
                    raise RuntimeError(
                        "Form was not found."
                    )

                message = (
                    f"Deleted form "
                    f"`{selected_form_key}`."
                )

                selected_form_key = ""

            else:
                raise RuntimeError(
                    "Unknown forms action."
                )

        forms: list[
            dict[str, str]
        ] = []

        text_channels: list[
            dict[str, str]
        ] = []

        selected_form = None
        questions = []

        verification_form_key = (
            FORM_KEY_VERIFICATION
        )

        modal_pages = 0

        if selected_guild is not None:
            text_channels = (
                context.guild_text_channels(
                    selected_guild
                )
            )

            forms = context.run_coro(
                get_guild_forms(
                    selected_guild
                )
            )

            verification_form_key = (
                settings_store
                .get_verification_form_key(
                    selected_guild.id
                )
                or FORM_KEY_VERIFICATION
            )

            if not selected_form_key:
                selected_form_key = (
                    verification_form_key
                )

            if (
                forms
                and not any(
                    form["key"]
                    == selected_form_key
                    for form in forms
                )
            ):
                selected_form_key = (
                    forms[0]["key"]
                )

            if selected_form_key:
                selected_form = (
                    context.run_coro(
                        form_store
                        .get_form_config(
                            guild_id=(
                                selected_guild.id
                            ),
                            form_key=(
                                selected_form_key
                            ),
                            fallback_json_path=(
                                VERIFICATION_FORM_PATH
                            ),
                        )
                    )
                )

                questions = (
                    context.run_coro(
                        form_store
                        .list_questions(
                            guild_id=(
                                selected_guild.id
                            ),
                            form_key=(
                                selected_form_key
                            ),
                            fallback_json_path=(
                                VERIFICATION_FORM_PATH
                            ),
                        )
                    )
                )

                modal_pages = len(
                    selected_form.pages()
                )

                forms = context.run_coro(
                    get_guild_forms(
                        selected_guild
                    )
                )

        return render_template(
            "forms/index.html",
            **context.template_context(
                title="TFSBot Forms",
                active_page="forms",
                guilds=(
                    context.available_guilds()
                ),
                selected_guild_id=(
                    str(
                        selected_guild.id
                    )
                    if selected_guild
                    else None
                ),
                forms=forms,
                selected_form_key=(
                    selected_form_key
                ),
                selected_form=(
                    selected_form
                ),
                questions=questions,
                text_channels=(
                    text_channels
                ),
                verification_form_key=(
                    verification_form_key
                ),
                modal_pages=modal_pages,
                uploaded_images=(
                    context.uploads
                    .list_images()
                ),
                message=message,
                error=error,
            ),
        )

    except Exception as caught_error:
        error = str(
            caught_error
        )

        return render_template(
            "forms/index.html",
            **context.template_context(
                title="TFSBot Forms",
                active_page="forms",
                guilds=(
                    context.available_guilds()
                ),
                selected_guild_id=(
                    str(
                        selected_guild.id
                    )
                    if selected_guild
                    else None
                ),
                forms=[],
                selected_form_key=(
                    selected_form_key
                ),
                selected_form=None,
                questions=[],
                text_channels=[],
                verification_form_key=(
                    FORM_KEY_VERIFICATION
                ),
                modal_pages=0,
                uploaded_images=[],
                message=message,
                error=error,
            ),
        )


@blueprint.route(
    "/forms/view",
    methods=[
        "GET",
    ],
)
def viewer():
    owner_error = require_owner()

    if owner_error is not None:
        return owner_error

    context = webui_context()

    selected_guild = (
        context.selected_guild(
            request.args.get(
                "guild_id"
            )
        )
    )

    selected_form_key = (
        clean_form_key(
            request.args.get(
                "form_key",
                "",
            )
        )
    )

    error: str | None = None

    try:
        if selected_guild is None:
            raise RuntimeError(
                "No server selected."
            )

        if not selected_form_key:
            raise RuntimeError(
                "No form selected."
            )

        form_store = (
            context.form_store()
        )

        form_config = (
            context.run_coro(
                form_store
                .get_form_config(
                    guild_id=(
                        selected_guild.id
                    ),
                    form_key=(
                        selected_form_key
                    ),
                    fallback_json_path=(
                        VERIFICATION_FORM_PATH
                    ),
                )
            )
        )

        pages: list[
            dict[str, Any]
        ] = []

        for (
            page_index,
            page_questions,
        ) in enumerate(
            form_config.pages(),
            start=1,
        ):
            page_rows: list[
                dict[str, Any]
            ] = []

            for (
                question_index,
                question,
            ) in enumerate(
                page_questions,
                start=1,
            ):
                min_text = (
                    str(
                        question.min_length
                    )
                    if (
                        question.min_length
                        is not None
                    )
                    else "No min"
                )

                max_text = (
                    str(
                        question.max_length
                    )
                    if (
                        question.max_length
                        is not None
                    )
                    else "No max"
                )

                page_rows.append(
                    {
                        "number": (
                            question_index
                        ),
                        "key": (
                            question.key
                        ),
                        "label": (
                            question.label
                        ),
                        "style": (
                            "Short answer"
                            if (
                                question.style
                                == discord.TextStyle.short
                            )
                            else "Paragraph"
                        ),
                        "required": (
                            question.required
                        ),
                        "placeholder": (
                            question.placeholder
                        ),
                        "limits": (
                            f"{min_text} / "
                            f"{max_text}"
                        ),
                    }
                )

            pages.append(
                {
                    "number": (
                        page_index
                    ),
                    "questions": (
                        page_rows
                    ),
                }
            )

        return render_template(
            "forms/viewer.html",
            **context.template_context(
                title="TFSBot Form Viewer",
                active_page="forms",
                selected_guild_id=(
                    str(
                        selected_guild.id
                    )
                ),
                form_key=(
                    selected_form_key
                ),
                form_title=(
                    form_config.title
                ),
                custom_id_prefix=(
                    form_config
                    .custom_id_prefix
                ),
                question_count=len(
                    form_config.questions
                ),
                page_count=len(
                    pages
                ),
                pages=pages,
                message=None,
                error=None,
            ),
        )

    except Exception as caught_error:
        error = str(
            caught_error
        )

        return render_template(
            "forms/viewer.html",
            **context.template_context(
                title="TFSBot Form Viewer",
                active_page="forms",
                selected_guild_id=(
                    str(
                        selected_guild.id
                    )
                    if selected_guild
                    else ""
                ),
                form_key=(
                    selected_form_key
                ),
                form_title="Unknown",
                custom_id_prefix="Unknown",
                question_count=0,
                page_count=0,
                pages=[],
                message=None,
                error=error,
            ),
        )
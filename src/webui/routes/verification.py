from __future__ import annotations

import discord

from flask import (
    Blueprint,
    render_template,
    request,
)

from src.commands.verification.verification import (
    VerifyView,
    cancel_all_pending_applications_for_guild,
    cancel_pending_application_by_user_id,
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
    "verification",
    __name__,
)


def parse_terms_from_text(
    raw_text: str,
) -> list[str]:
    terms: list[str] = []

    for raw_line in raw_text.splitlines():
        stripped = raw_line.strip()

        if (
            not stripped
            or stripped.startswith("#")
        ):
            continue

        terms.append(
            stripped
        )

    return terms


def get_current_settings(
    guild: discord.Guild,
) -> dict[str, str | bool]:
    context = webui_context()

    settings_store = (
        context.guild_settings_store()
    )

    return {
        "review_channel_id": str(
            settings_store
            .get_review_channel_id(
                guild.id
            )
            or ""
        ),
        "log_channel_id": str(
            settings_store
            .get_application_log_channel_id(
                guild.id
            )
            or ""
        ),
        "verification_form_key": (
            settings_store
            .get_verification_form_key(
                guild.id
            )
            or FORM_KEY_VERIFICATION
        ),
        "approved_add_role_id": str(
            settings_store
            .get_approved_add_role_id(
                guild.id
            )
            or ""
        ),
        "approved_remove_role_id": str(
            settings_store
            .get_approved_remove_role_id(
                guild.id
            )
            or ""
        ),
        "automod_enabled": (
            settings_store
            .is_automod_enabled(
                guild.id
            )
        ),
    }


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
                "key": (
                    FORM_KEY_VERIFICATION
                ),
                "title": "Verification",
            },
        )

    return forms


async def post_verification_panel(
    guild: discord.Guild,
    channel_id: int,
    form_key: str,
    image_upload_filename: (
        str | None
    ) = None,
    thumbnail_upload_filename: (
        str | None
    ) = None,
) -> None:
    context = webui_context()

    bot = context.bot

    channel = guild.get_channel(
        channel_id
    )

    if channel is None:
        fetched_channel = (
            await bot.fetch_channel(
                channel_id
            )
        )

    else:
        fetched_channel = channel

    if not isinstance(
        fetched_channel,
        discord.TextChannel,
    ):
        raise RuntimeError(
            "Selected panel channel "
            "is not a text channel."
        )

    form_store = (
        context.form_store()
    )

    form_config = (
        await form_store.get_form_config(
            guild_id=guild.id,
            form_key=form_key,
            fallback_json_path=(
                VERIFICATION_FORM_PATH
            ),
        )
    )

    embed = discord.Embed(
        title=(
            f"{guild.name} Verification"
        ),
        description=(
            "Welcome!\n\n"
            "Please complete the "
            f"**{discord.utils.escape_markdown(form_config.title)}** "
            "form to apply for access "
            "to the server.\n\n"
            "Click the button below "
            "to begin."
        ),
        colour=discord.Colour.blurple(),
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
                image_upload_filename
            ),
            thumbnail_reference=(
                thumbnail_upload_filename
            ),
        )
    )

    if thumbnail_attachment_url:
        embed.set_thumbnail(
            url=thumbnail_attachment_url
        )

    elif guild.icon is not None:
        embed.set_thumbnail(
            url=guild.icon.url
        )

    if image_attachment_url:
        embed.set_image(
            url=image_attachment_url
        )

    embed.set_footer(
        text="TFSBot Verification"
    )

    try:
        await fetched_channel.send(
            embed=embed,
            view=VerifyView(),
            files=(
                files
                if files
                else None
            ),
        )

    finally:
        context.uploads.close_files(
            files
        )


@blueprint.route(
    "/verification",
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

    try:
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
                "save_verification",
            )

            if action in {
                "cancel_by_user",
                "cancel_all_pending",
            }:
                if context.bot.user is None:
                    raise RuntimeError(
                        "Bot user is not "
                        "available yet."
                    )

                if (
                    request.form.get(
                        "cancel_confirm",
                        "",
                    ).strip()
                    != "CANCEL"
                ):
                    raise RuntimeError(
                        "Type CANCEL in the "
                        "confirmation field to "
                        "cancel applications."
                    )

                cancellation_reason = (
                    request.form.get(
                        "cancel_reason",
                        "",
                    ).strip()
                )

                if not cancellation_reason:
                    cancellation_reason = (
                        "Manually cancelled "
                        "from the WebUI."
                    )

                if (
                    action
                    == "cancel_by_user"
                ):
                    user_id_text = (
                        request.form.get(
                            "cancel_user_id",
                            "",
                        ).strip()
                    )

                    if not user_id_text:
                        raise RuntimeError(
                            "Enter a user ID "
                            "to cancel by user."
                        )

                    try:
                        user_id = int(
                            user_id_text
                        )

                    except ValueError as caught:
                        raise RuntimeError(
                            "User ID must "
                            "be a number."
                        ) from caught

                    result = (
                        context.run_coro(
                            cancel_pending_application_by_user_id(
                                client=(
                                    context.bot
                                ),
                                guild_id=(
                                    selected_guild.id
                                ),
                                user_id=user_id,
                                moderator=(
                                    context.bot.user
                                ),
                                reason=(
                                    cancellation_reason
                                ),
                            )
                        )
                    )

                else:
                    result = (
                        context.run_coro(
                            cancel_all_pending_applications_for_guild(
                                client=(
                                    context.bot
                                ),
                                guild_id=(
                                    selected_guild.id
                                ),
                                moderator=(
                                    context.bot.user
                                ),
                                reason=(
                                    cancellation_reason
                                ),
                            )
                        )
                    )

                message = result.detail

            elif action == "refresh_invites":
                invite_tracker = (
                    context
                    .invite_tracker_store()
                )

                refreshed = (
                    context.run_coro(
                        invite_tracker
                        .sync_guild_invites(
                            selected_guild
                        )
                    )
                )

                if refreshed:
                    message = (
                        "Invite cache "
                        "refreshed."
                    )

                else:
                    message = (
                        "Could not refresh "
                        "invites. Check the bot "
                        "has Manage Server."
                    )

            else:
                review_channel_id = (
                    request.form.get(
                        "review_channel_id",
                        "",
                    ).strip()
                )

                log_channel_id = (
                    request.form.get(
                        "log_channel_id",
                        "",
                    ).strip()
                )

                verification_form_key = (
                    request.form.get(
                        "verification_form_key",
                        FORM_KEY_VERIFICATION,
                    ).strip()
                    or FORM_KEY_VERIFICATION
                )

                approved_add_role_id = (
                    request.form.get(
                        "approved_add_role_id",
                        "",
                    ).strip()
                )

                approved_remove_role_id = (
                    request.form.get(
                        "approved_remove_role_id",
                        "",
                    ).strip()
                )

                if review_channel_id:
                    settings_store.set_review_channel_id(
                        selected_guild.id,
                        int(
                            review_channel_id
                        ),
                    )

                if log_channel_id:
                    settings_store.set_application_log_channel_id(
                        selected_guild.id,
                        int(
                            log_channel_id
                        ),
                    )

                settings_store.set_verification_form_key(
                    selected_guild.id,
                    verification_form_key,
                )

                if approved_add_role_id:
                    settings_store.set_approved_add_role_id(
                        selected_guild.id,
                        int(
                            approved_add_role_id
                        ),
                    )

                else:
                    settings_store.clear_approved_add_role_id(
                        selected_guild.id
                    )

                if approved_remove_role_id:
                    settings_store.set_approved_remove_role_id(
                        selected_guild.id,
                        int(
                            approved_remove_role_id
                        ),
                    )

                else:
                    settings_store.clear_approved_remove_role_id(
                        selected_guild.id
                    )

                settings_store.set_automod_enabled(
                    selected_guild.id,
                    (
                        request.form.get(
                            "automod_enabled"
                        )
                        == "on"
                    ),
                )

                if (
                    action
                    == "clear_automod_terms"
                ):
                    settings_store.clear_automod_terms(
                        selected_guild.id
                    )

                    message = (
                        "Verification settings "
                        "saved and automod "
                        "terms cleared."
                    )

                else:
                    terms = (
                        parse_terms_from_text(
                            request.form.get(
                                "automod_terms",
                                "",
                            )
                        )
                    )

                    settings_store.set_automod_terms(
                        selected_guild.id,
                        terms,
                    )

                    if (
                        action
                        == "add_default_terms"
                    ):
                        added_count = (
                            settings_store
                            .add_default_automod_terms(
                                selected_guild.id
                            )
                        )

                        message = (
                            "Verification settings "
                            "saved. Added "
                            f"{added_count} default "
                            "automod term(s)."
                        )

                    else:
                        message = (
                            "Verification settings "
                            "saved."
                        )

                if (
                    action
                    == "save_and_post_panel"
                ):
                    panel_channel_id = (
                        request.form.get(
                            "panel_channel_id",
                            "",
                        ).strip()
                    )

                    if not panel_channel_id:
                        raise RuntimeError(
                            "Choose a panel "
                            "channel before "
                            "posting the "
                            "verification panel."
                        )

                    context.run_coro(
                        post_verification_panel(
                            guild=selected_guild,
                            channel_id=int(
                                panel_channel_id
                            ),
                            form_key=(
                                verification_form_key
                            ),
                            image_upload_filename=(
                                request.form.get(
                                    "panel_image_upload_filename"
                                )
                                or None
                            ),
                            thumbnail_upload_filename=(
                                request.form.get(
                                    "panel_thumbnail_upload_filename"
                                )
                                or None
                            ),
                        )
                    )

                    message = (
                        "Verification settings "
                        "saved and panel posted."
                    )

        roles: list[
            dict[str, str]
        ] = []

        text_channels: list[
            dict[str, str]
        ] = []

        forms: list[
            dict[str, str]
        ] = []

        settings: dict[
            str,
            str | bool,
        ] = {}

        automod_terms_text = ""

        default_terms: list[str] = []

        if selected_guild is not None:
            roles = (
                context.guild_roles(
                    selected_guild
                )
            )

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

            settings = (
                get_current_settings(
                    selected_guild
                )
            )

            automod_terms_text = (
                "\n".join(
                    settings_store
                    .list_automod_terms(
                        selected_guild.id
                    )
                )
            )

            default_terms = (
                settings_store
                .get_default_automod_terms()
            )

        invite_tracking_status = (
            "Ready"
            if getattr(
                context.bot,
                "invite_tracker_ready",
                False,
            )
            else (
                "Starting / not "
                "synced yet"
            )
        )

        return render_template(
            "verification/index.html",
            **context.template_context(
                title="TFSBot Verification",
                active_page="verification",
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
                roles=roles,
                text_channels=(
                    text_channels
                ),
                forms=forms,
                settings=settings,
                automod_terms_text=(
                    automod_terms_text
                ),
                default_terms=(
                    default_terms
                ),
                default_terms_text=(
                    "\n".join(
                        default_terms
                    )
                ),
                invite_tracking_status=(
                    invite_tracking_status
                ),
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
            "verification/index.html",
            **context.template_context(
                title="TFSBot Verification",
                active_page="verification",
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
                roles=[],
                text_channels=[],
                forms=[],
                settings={},
                automod_terms_text="",
                default_terms=[],
                default_terms_text="",
                invite_tracking_status=(
                    "Unknown"
                ),
                uploaded_images=[],
                message=message,
                error=error,
            ),
        )
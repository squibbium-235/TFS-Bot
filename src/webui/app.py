from __future__ import annotations

import threading

import discord
from flask import Flask

from src.webui.context import (
    WebUIContext,
)
from src.webui.helpers import (
    WEBUI_CONTEXT_KEY,
)
from src.webui.routes import (
    register_blueprints,
)


def build_secret_key(
    bot: discord.Client,
) -> str:
    secret_parts = [
        (
            f"{credential.username}:"
            f"{credential.password}"
        )
        for credential
        in bot.config.webui_credentials
    ]

    discord_client_secret = getattr(
        bot.config,
        "discord_oauth_client_secret",
        "",
    )

    if discord_client_secret:
        secret_parts.append(
            discord_client_secret
        )

    return (
        "|".join(
            secret_parts
        )
        or "tfsbot-dev-secret"
    )


def create_webui(
    bot: discord.Client,
) -> Flask:
    app = Flask(
        __name__
    )

    web_context = WebUIContext(
        bot
    )

    app.extensions[
        WEBUI_CONTEXT_KEY
    ] = web_context

    app.secret_key = (
        build_secret_key(
            bot
        )
    )

    app.config[
        "MAX_CONTENT_LENGTH"
    ] = (
        10
        * 1024
        * 1024
    )

    register_blueprints(
        app
    )

    return app


def start_webui(
    bot: discord.Client,
) -> None:
    if not (
        bot.config.webui_enabled
    ):
        return

    app = create_webui(
        bot
    )

    thread = threading.Thread(
        target=lambda: app.run(
            host=(
                bot.config.webui_host
            ),
            port=(
                bot.config.webui_port
            ),
            debug=False,
            use_reloader=False,
        ),
        daemon=True,
    )

    thread.start()
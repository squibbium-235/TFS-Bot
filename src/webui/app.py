"""Flask Web UI created inside the bot process and served by waitress.

start_webui runs waitress on a daemon thread, so the server stops when the
bot process exits. The session cookie is httponly with SameSite=Lax. Logged-in
sessions last eight hours from authentication and one hour from the last
request; a missing timestamp clears the session. Successful POSTs are audited
after the response is built.
"""

from __future__ import annotations

import threading
import time

from datetime import timedelta

from waitress import serve

import discord

from flask import (
    Flask,
    redirect,
    request,
    session,
    url_for,
)

from src.webui.context import (
    WebUIContext,
)
from src.webui.csrf import (
    csrf_token,
    validate_csrf,
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
    """Join WebUI passwords with the Discord OAuth client secret.

    Each credential becomes ``username:password``. A non-empty client secret
    is appended, and the parts are joined with ``|``. If that string is
    empty the literal ``tfsbot-dev-secret`` is returned. This function does
    not read the auth flags; it only uses values already on the bot.
    """
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
    """Build the Flask app, session policy, CSRF hooks, and blueprints.

    Uploads are capped at 10 MiB. ``PERMANENT_SESSION_LIFETIME`` is eight
    hours; the idle limit is enforced separately because Flask does not
    track it. ``csrf_token`` is injected as a callable so a template
    reference creates a session token on first use.
    """
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

    app.config.update(
        MAX_CONTENT_LENGTH=(
            10
            * 1024
            * 1024
        ),
        PERMANENT_SESSION_LIFETIME=(
            timedelta(
                hours=8
            )
        ),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    @app.before_request
    def enforce_session_lifetime():
        """Expire logged-in sessions and refresh the idle clock.

        ``logged_in`` must be exactly True. Missing or non-numeric
        timestamps always clear the session and redirect to login. An
        expired session redirects too, except when the request is already
        the login page, so that page can render after the cookie is
        cleared. Activity refreshes ``last_activity`` only; it does not
        move ``authenticated_at``.
        """
        if not (
            session.get(
                "logged_in"
            )
            is True
        ):
            return None

        now = int(
            time.time()
        )

        try:
            authenticated_at = int(
                session[
                    "authenticated_at"
                ]
            )

            last_activity = int(
                session[
                    "last_activity"
                ]
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            session.clear()

            return redirect(
                url_for(
                    "auth.login"
                )
            )

        absolute_age = (
            now
            - authenticated_at
        )

        idle_age = (
            now
            - last_activity
        )

        if (
            absolute_age
            > 8 * 60 * 60
            or idle_age
            > 60 * 60
        ):
            session.clear()

            if (
                request.endpoint
                == "auth.login"
            ):
                return None

            return redirect(
                url_for(
                    "auth.login"
                )
            )

        session[
            "last_activity"
        ] = now

        session.permanent = True

        return None

    app.before_request(
        validate_csrf
    )

    @app.context_processor
    def inject_csrf_token():
        """Expose csrf_token() to every template, including the login page."""
        return {
            "csrf_token": (
                csrf_token()
            )
        }

    @app.after_request
    def audit_webui_change(
        response,
    ):
        """Record a successful logged-in POST without failing the response.

        The action name prefers the form ``action`` field, then the
        endpoint. ``guild_id`` is recorded only when that form field is a
        valid integer. An audit-store failure is logged and swallowed.
        Routes that write their own audit row still pass through here.
        """
        if (
            request.method
            == "POST"
            and response.status_code
            < 400
            and session.get(
                "logged_in"
            )
            is True
        ):
            action = (
                request.form.get(
                    "action"
                )
                or request.endpoint
                or "unknown"
            )

            guild_id = None

            try:
                raw_guild_id = (
                    request.form.get(
                        "guild_id"
                    )
                )

                if raw_guild_id:
                    guild_id = int(
                        raw_guild_id
                    )

            except (
                TypeError,
                ValueError,
            ):
                guild_id = None

            try:
                web_context.audit(
                    action=(
                        f"webui.{action}"
                    ),
                    guild_id=guild_id,
                    detail=(
                        request.endpoint
                        or ""
                    ),
                )

            except Exception:
                bot.log.exception(
                    "Failed to write "
                    "WebUI audit entry."
                )

        return response

    register_blueprints(
        app
    )

    return app


def start_webui(
    bot: discord.Client,
) -> None:
    """Start waitress on a daemon thread when the Web UI is enabled.

    A disabled Web UI returns before the app is built. The thread is not
    joined; process shutdown is what stops it.
    """
    if not bot.config.webui_enabled:
        return

    app = create_webui(
        bot
    )

    thread = threading.Thread(
        target=lambda: serve(
            app,
            host=bot.config.webui_host,
            port=bot.config.webui_port,
            threads=8,
        ),
        daemon=True,
        name="TFSBot-WebUI",
    )

    thread.start()
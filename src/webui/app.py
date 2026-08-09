from __future__ import annotations

import hmac
import json
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import discord
from flask import (
    Flask,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)

from src.webui.context import (
    WebUIContext,
)
from src.webui.helpers import (
    WEBUI_CONTEXT_KEY,
)

from src.webui.routes import (
    register_blueprints,
)


LOGIN_HTML = """
<!doctype html>
<html>
<head>
    <title>TFSBot Login</title>
    <style>
        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: #111318;
            color: #f2f3f5;
            display: grid;
            place-items: center;
            height: 100vh;
        }

        .card {
            background: #1e2129;
            padding: 28px;
            border-radius: 16px;
            width: 360px;
            box-shadow: 0 18px 50px rgba(0, 0, 0, 0.35);
        }

        input, button {
            width: 100%;
            box-sizing: border-box;
            padding: 12px;
            border-radius: 10px;
            border: 1px solid #3a3f4b;
            background: #151820;
            color: #f2f3f5;
            margin-top: 8px;
        }

        button {
            background: #5865f2;
            border: 0;
            cursor: pointer;
            font-weight: bold;
        }

        .discord-button {
            background: #5865f2;
        }

        .divider {
            display: flex;
            align-items: center;
            gap: 10px;
            color: #b5bac1;
            font-size: 13px;
            margin: 20px 0 12px;
        }

        .divider::before,
        .divider::after {
            content: "";
            flex: 1;
            height: 1px;
            background: #3a3f4b;
        }

        .error {
            color: #ff6b6b;
        }

        .hint {
            color: #b5bac1;
            font-size: 13px;
            line-height: 1.45;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>TFSBot Web UI</h1>

        {% if discord_login_enabled %}
            <form method="get" action="{{ url_for('discord_login_start') }}">
                <button type="submit" class="discord-button">Login with Discord</button>
            </form>

            <p class="hint">
                Access is granted only if your Discord account has an allowed server role.
            </p>
        {% endif %}

        {% if discord_login_enabled and password_login_enabled %}
            <div class="divider">or emergency login</div>
        {% endif %}

        {% if password_login_enabled %}
            <form method="post">
                <label>Username</label>
                <input type="text" name="username" autocomplete="username" {% if not discord_login_enabled %}autofocus{% endif %}>

                <label>Password</label>
                <input type="password" name="password" autocomplete="current-password">

                <button type="submit">Login</button>
            </form>
        {% endif %}

        {% if not discord_login_enabled and not password_login_enabled %}
            <p class="error">No WebUI login methods are configured.</p>
        {% endif %}

        {% if error %}
            <p class="error">{{ error }}</p>
        {% endif %}
    </div>
</body>
</html>
"""

def create_webui(bot: discord.Client) -> Flask:
    app = Flask(__name__)
    
    web_context = WebUIContext(
        bot
    )

    app.extensions[
        WEBUI_CONTEXT_KEY
    ] = web_context

    secret_parts = [
        f"{credential.username}:{credential.password}"
        for credential in bot.config.webui_credentials
    ]

    discord_client_secret = getattr(
        bot.config,
        "discord_oauth_client_secret",
        "",
    )

    if discord_client_secret:
        secret_parts.append(discord_client_secret)

    app.secret_key = "|".join(secret_parts) or "tfsbot-dev-secret"

    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

    is_discord_login_enabled = (
        web_context
        .access
        .discord_login_enabled
    )

    is_password_login_enabled = (
        web_context
        .access
        .password_login_enabled
    )

    def render_login_page(error: str | None = None) -> str:
        return render_template_string(
            LOGIN_HTML,
            error=error,
            discord_login_enabled=is_discord_login_enabled(),
            password_login_enabled=is_password_login_enabled(),
        )

    def get_discord_authorisation_url(state: str) -> str:
        query = urllib.parse.urlencode(
            {
                "client_id": str(bot.config.discord_oauth_client_id),
                "redirect_uri": bot.config.discord_oauth_redirect_uri,
                "response_type": "code",
                "scope": "identify guilds.members.read",
                "state": state,
            }
        )

        return f"https://discord.com/oauth2/authorize?{query}"

    def discord_api_request(
        url: str,
        method: str = "GET",
        data: dict[str, str] | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        body: bytes | None = None
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "TFSBot WebUI",
        }

        if data is not None:
            body = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        if access_token is not None:
            headers["Authorization"] = f"Bearer {access_token}"

        request_object = urllib.request.Request(
            url=url,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(request_object, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))

        except urllib.error.HTTPError as error:
            try:
                error_body = error.read().decode("utf-8")
            except Exception:
                error_body = ""

            raise RuntimeError(
                f"Discord API request failed: HTTP {error.code} {error_body}"
            ) from error

        except urllib.error.URLError as error:
            raise RuntimeError(f"Discord API request failed: {error}") from error

    def exchange_discord_code_for_token(code: str) -> str:
        token_data = discord_api_request(
            url="https://discord.com/api/oauth2/token",
            method="POST",
            data={
                "client_id": str(bot.config.discord_oauth_client_id),
                "client_secret": bot.config.discord_oauth_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": bot.config.discord_oauth_redirect_uri,
            },
        )

        access_token = token_data.get("access_token")

        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("Discord did not return an access token.")

        return access_token

    def fetch_discord_user(access_token: str) -> dict[str, Any]:
        return discord_api_request(
            url="https://discord.com/api/users/@me",
            access_token=access_token,
        )

    def fetch_discord_member(access_token: str) -> dict[str, Any]:
        guild_id = bot.config.webui_discord_guild_id

        if guild_id is None:
            raise RuntimeError("WEBUI_DISCORD_GUILD_ID is not configured.")

        return discord_api_request(
            url=f"https://discord.com/api/users/@me/guilds/{guild_id}/member",
            access_token=access_token,
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_login_page(error=None)

        if not is_password_login_enabled():
            return render_login_page(error="Emergency username/password login is disabled.")

        username = request.form.get("username", "")
        password = request.form.get("password", "")

        login_ok = any(
            hmac.compare_digest(username, credential.username)
            and hmac.compare_digest(password, credential.password)
            for credential in bot.config.webui_credentials
        )

        if not login_ok:
            return render_login_page(error="Incorrect username or password.")

        session.clear()
        session["logged_in"] = True
        session["auth_method"] = "password"
        session["username"] = username
        session["display_name"] = username
        session["webui_role"] = "owner"

        return redirect(url_for("overview.index"))

    @app.route("/auth/discord/start")
    def discord_login_start():
        if not is_discord_login_enabled():
            return render_login_page(error="Discord login is not enabled.")

        state = secrets.token_urlsafe(32)
        session["discord_oauth_state"] = state

        return redirect(get_discord_authorisation_url(state=state))

    @app.route("/auth/discord/callback")
    def discord_login_callback():
        if not is_discord_login_enabled():
            return render_login_page(error="Discord login is not enabled.")

        oauth_error = request.args.get("error")

        if oauth_error:
            return render_login_page(error=f"Discord login failed: {oauth_error}")

        code = request.args.get("code", "")
        state = request.args.get("state", "")
        expected_state = session.pop("discord_oauth_state", "")

        if not code:
            return render_login_page(error="Discord did not return an authorisation code.")

        if not hmac.compare_digest(state, expected_state):
            return render_login_page(error="Discord login state mismatch. Try again.")

        try:
            access_token = exchange_discord_code_for_token(code=code)
            user_data = fetch_discord_user(access_token=access_token)
            member_data = fetch_discord_member(access_token=access_token)

            webui_role = (
                web_context
                .access
                .matching_discord_role(
                    member_data
                )
            )

            if webui_role is None:
                return render_login_page(
                    error="Your Discord account does not have an allowed WebUI role."
                )

            username = str(user_data.get("username") or "Discord user")
            global_name = str(user_data.get("global_name") or "").strip()
            user_id = str(user_data.get("id") or "")

            display_name = global_name or username

            session.clear()
            session["logged_in"] = True
            session["auth_method"] = "discord"
            session["discord_user_id"] = user_id
            session["discord_username"] = username
            session["display_name"] = display_name
            session["webui_role"] = webui_role

            return redirect(url_for("overview.index"))

        except Exception as error:
            return render_login_page(error=str(error))

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    register_blueprints(
        app
    )

    return app


def start_webui(bot: discord.Client) -> None:
    if not bot.config.webui_enabled:
        return

    app = create_webui(bot)

    thread = threading.Thread(
        target=lambda: app.run(
            host=bot.config.webui_host,
            port=bot.config.webui_port,
            debug=False,
            use_reloader=False,
        ),
        daemon=True,
    )

    thread.start()
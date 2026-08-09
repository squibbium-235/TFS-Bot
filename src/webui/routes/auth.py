from __future__ import annotations

import hmac
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from src.webui.helpers import (
    webui_context,
)


blueprint = Blueprint(
    "auth",
    __name__,
)


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
        body = urllib.parse.urlencode(
            data
        ).encode(
            "utf-8"
        )

        headers[
            "Content-Type"
        ] = (
            "application/"
            "x-www-form-urlencoded"
        )

    if access_token is not None:
        headers[
            "Authorization"
        ] = (
            f"Bearer {access_token}"
        )

    request_object = (
        urllib.request.Request(
            url=url,
            data=body,
            headers=headers,
            method=method,
        )
    )

    try:
        with urllib.request.urlopen(
            request_object,
            timeout=15,
        ) as response:
            return json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except urllib.error.HTTPError as error:
        try:
            error_body = (
                error.read().decode(
                    "utf-8"
                )
            )

        except Exception:
            error_body = ""

        raise RuntimeError(
            "Discord API request failed: "
            f"HTTP {error.code} "
            f"{error_body}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            "Discord API request failed: "
            f"{error}"
        ) from error


def get_discord_authorisation_url(
    state: str,
) -> str:
    context = webui_context()

    query = urllib.parse.urlencode(
        {
            "client_id": str(
                context
                .bot
                .config
                .discord_oauth_client_id
            ),
            "redirect_uri": (
                context
                .bot
                .config
                .discord_oauth_redirect_uri
            ),
            "response_type": "code",
            "scope": (
                "identify "
                "guilds.members.read"
            ),
            "state": state,
        }
    )

    return (
        "https://discord.com/"
        "oauth2/authorize?"
        f"{query}"
    )


def exchange_discord_code_for_token(
    code: str,
) -> str:
    context = webui_context()

    token_data = discord_api_request(
        url=(
            "https://discord.com/"
            "api/oauth2/token"
        ),
        method="POST",
        data={
            "client_id": str(
                context
                .bot
                .config
                .discord_oauth_client_id
            ),
            "client_secret": (
                context
                .bot
                .config
                .discord_oauth_client_secret
            ),
            "grant_type": (
                "authorization_code"
            ),
            "code": code,
            "redirect_uri": (
                context
                .bot
                .config
                .discord_oauth_redirect_uri
            ),
        },
    )

    access_token = token_data.get(
        "access_token"
    )

    if (
        not isinstance(
            access_token,
            str,
        )
        or not access_token
    ):
        raise RuntimeError(
            "Discord did not return "
            "an access token."
        )

    return access_token


def fetch_discord_user(
    access_token: str,
) -> dict[str, Any]:
    return discord_api_request(
        url=(
            "https://discord.com/"
            "api/users/@me"
        ),
        access_token=access_token,
    )


def fetch_discord_member(
    access_token: str,
) -> dict[str, Any]:
    context = webui_context()

    guild_id = (
        context
        .bot
        .config
        .webui_discord_guild_id
    )

    if guild_id is None:
        raise RuntimeError(
            "WEBUI_DISCORD_GUILD_ID "
            "is not configured."
        )

    return discord_api_request(
        url=(
            "https://discord.com/"
            "api/users/@me/guilds/"
            f"{guild_id}/member"
        ),
        access_token=access_token,
    )


def render_login_page(
    error: str | None = None,
) -> str:
    context = webui_context()

    return render_template(
        "auth/login.html",
        error=error,
        discord_login_enabled=(
            context
            .access
            .discord_login_enabled()
        ),
        password_login_enabled=(
            context
            .access
            .password_login_enabled()
        ),
    )


@blueprint.route(
    "/login",
    methods=[
        "GET",
        "POST",
    ],
)
def login():
    context = webui_context()

    if request.method == "GET":
        return render_login_page()

    if not (
        context
        .access
        .password_login_enabled()
    ):
        return render_login_page(
            error=(
                "Emergency username/"
                "password login is "
                "disabled."
            )
        )

    username = request.form.get(
        "username",
        "",
    )

    password = request.form.get(
        "password",
        "",
    )

    login_ok = any(
        hmac.compare_digest(
            username,
            credential.username,
        )
        and hmac.compare_digest(
            password,
            credential.password,
        )
        for credential
        in (
            context
            .bot
            .config
            .webui_credentials
        )
    )

    if not login_ok:
        return render_login_page(
            error=(
                "Incorrect username "
                "or password."
            )
        )

    session.clear()

    session["logged_in"] = True
    session["auth_method"] = (
        "password"
    )
    session["username"] = username
    session["display_name"] = username
    session["webui_role"] = "owner"

    return redirect(
        url_for(
            "overview.index"
        )
    )


@blueprint.route(
    "/auth/discord/start"
)
def discord_login_start():
    context = webui_context()

    if not (
        context
        .access
        .discord_login_enabled()
    ):
        return render_login_page(
            error=(
                "Discord login is "
                "not enabled."
            )
        )

    state = secrets.token_urlsafe(
        32
    )

    session[
        "discord_oauth_state"
    ] = state

    return redirect(
        get_discord_authorisation_url(
            state
        )
    )


@blueprint.route(
    "/auth/discord/callback"
)
def discord_login_callback():
    context = webui_context()

    if not (
        context
        .access
        .discord_login_enabled()
    ):
        return render_login_page(
            error=(
                "Discord login is "
                "not enabled."
            )
        )

    oauth_error = request.args.get(
        "error"
    )

    if oauth_error:
        return render_login_page(
            error=(
                "Discord login failed: "
                f"{oauth_error}"
            )
        )

    code = request.args.get(
        "code",
        "",
    )

    state = request.args.get(
        "state",
        "",
    )

    expected_state = session.pop(
        "discord_oauth_state",
        "",
    )

    if not code:
        return render_login_page(
            error=(
                "Discord did not return "
                "an authorisation code."
            )
        )

    if (
        not state
        or not expected_state
        or not hmac.compare_digest(
            state,
            expected_state,
        )
    ):
        return render_login_page(
            error=(
                "Discord login state "
                "mismatch. Try again."
            )
        )

    try:
        access_token = (
            exchange_discord_code_for_token(
                code
            )
        )

        user_data = fetch_discord_user(
            access_token
        )

        member_data = (
            fetch_discord_member(
                access_token
            )
        )

        webui_role = (
            context
            .access
            .matching_discord_role(
                member_data
            )
        )

        if webui_role is None:
            return render_login_page(
                error=(
                    "Your Discord account "
                    "does not have an "
                    "allowed WebUI role."
                )
            )

        username = str(
            user_data.get(
                "username"
            )
            or "Discord user"
        )

        global_name = str(
            user_data.get(
                "global_name"
            )
            or ""
        ).strip()

        user_id = str(
            user_data.get(
                "id"
            )
            or ""
        )

        display_name = (
            global_name
            or username
        )

        session.clear()

        session[
            "logged_in"
        ] = True

        session[
            "auth_method"
        ] = "discord"

        session[
            "discord_user_id"
        ] = user_id

        session[
            "discord_username"
        ] = username

        session[
            "display_name"
        ] = display_name

        session[
            "webui_role"
        ] = webui_role

        return redirect(
            url_for(
                "overview.index"
            )
        )

    except Exception as error:
        return render_login_page(
            error=str(
                error
            )
        )


@blueprint.route(
    "/logout"
)
def logout():
    session.clear()

    return redirect(
        url_for(
            "auth.login"
        )
    )
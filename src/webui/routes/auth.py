"""
Password login and Discord OAuth for the
Sanctuary Servo Web UI.

Password login compares the submitted
credentials with WEBUI_USER_1 and
WEBUI_USER_2 and starts an owner session.

Discord login uses the configured Web UI
guild to determine whether the user may log
in and whether they are an owner or viewer.

After authentication, Sanctuary Servo checks
its own Discord guilds to determine which of
them the authenticated user is actually a
member of. Only those shared guild IDs are
stored in the Web UI session.
"""

from __future__ import annotations

import hmac
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import discord

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
) -> Any:
    """
    Call the Discord API with urllib.

    Form bodies are URL encoded.

    An OAuth access token, when supplied, is
    sent as a Bearer token.

    HTTP and network errors are converted to
    RuntimeError so the login page can display
    a controlled error message.
    """
    body: bytes | None = None

    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "Sanctuary Servo WebUI",
    }

    if data is not None:
        body = urllib.parse.urlencode(
            data
        ).encode(
            "utf-8"
        )

        headers["Content-Type"] = (
            "application/"
            "x-www-form-urlencoded"
        )

    if access_token is not None:
        headers["Authorization"] = (
            f"Bearer {access_token}"
        )

    request_object = urllib.request.Request(
        url=url,
        data=body,
        headers=headers,
        method=method,
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


def get_discord_redirect_uri() -> str:
    """
    Use a localhost callback during local
    development.

    Other hosts use the redirect URI from
    configuration.
    """
    context = webui_context()

    hostname = (
        request
        .host
        .split(
            ":",
            1,
        )[0]
        .lower()
    )

    if hostname == "localhost":
        return (
            "http://localhost:"
            f"{context.bot.config.webui_port}"
            "/auth/discord/callback"
        )

    return (
        context
        .bot
        .config
        .discord_oauth_redirect_uri
    )


def get_discord_authorisation_url(
    state: str,
    redirect_uri: str,
) -> str:
    """
    Build the Discord OAuth URL.

    identify gives us the user's Discord ID.

    guilds.members.read allows Sanctuary Servo
    to retrieve the user's member object from
    the configured Web UI guild for role
    authentication.

    The general guilds scope is deliberately
    not required. Shared guild access is
    determined by the bot itself.
    """
    context = webui_context()

    query = urllib.parse.urlencode(
        {
            "client_id": str(
                context
                .bot
                .config
                .discord_oauth_client_id
            ),
            "redirect_uri": redirect_uri,
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
    redirect_uri: str,
) -> str:
    """
    Exchange a Discord OAuth authorisation
    code for an access token.
    """
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
            "redirect_uri": redirect_uri,
        },
    )

    if not isinstance(
        token_data,
        dict,
    ):
        raise RuntimeError(
            "Discord returned an invalid "
            "OAuth token response."
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
    """
    Fetch the currently authenticated Discord
    user.
    """
    user_data = discord_api_request(
        url=(
            "https://discord.com/"
            "api/users/@me"
        ),
        access_token=access_token,
    )

    if not isinstance(
        user_data,
        dict,
    ):
        raise RuntimeError(
            "Discord returned an invalid "
            "user response."
        )

    return user_data


def fetch_discord_member(
    access_token: str,
) -> dict[str, Any]:
    """
    Fetch the authenticated user's member
    object from WEBUI_DISCORD_GUILD_ID.

    This is used only to determine whether
    they have an allowed Web UI role.
    """
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

    member_data = discord_api_request(
        url=(
            "https://discord.com/"
            "api/users/@me/guilds/"
            f"{guild_id}/member"
        ),
        access_token=access_token,
    )

    if not isinstance(
        member_data,
        dict,
    ):
        raise RuntimeError(
            "Discord returned an invalid "
            "guild-member response."
        )

    return member_data


async def shared_bot_guild_ids(
    user_id: int,
) -> list[str]:
    """
    Return guild IDs shared by Sanctuary Servo
    and the authenticated Discord user.

    The member cache is checked first.

    If the member is not cached, Discord is
    queried directly through the bot account.

    NotFound means the user is not a member.

    Forbidden also fails closed for that guild
    rather than exposing its existence.

    A general Discord HTTP failure aborts login
    because we cannot safely determine access.
    """
    context = webui_context()

    visible_guild_ids: list[str] = []

    for guild in list(
        context.bot.guilds
    ):
        member = guild.get_member(
            user_id
        )

        if member is not None:
            visible_guild_ids.append(
                str(guild.id)
            )

            continue

        try:
            await guild.fetch_member(
                user_id
            )

        except discord.NotFound:
            continue

        except discord.Forbidden:
            # Fail closed. If the bot cannot
            # verify membership, do not expose
            # the guild through the Web UI.
            continue

        except discord.HTTPException as error:
            raise RuntimeError(
                "Sanctuary Servo could not "
                "verify your server membership "
                "with Discord. Try again."
            ) from error

        visible_guild_ids.append(
            str(guild.id)
        )

    visible_guild_ids.sort(
        key=int
    )

    return visible_guild_ids


def render_login_page(
    error: str | None = None,
) -> str:
    """
    Render the standalone login page.
    """
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


def render_login_failure(
    error: str,
):
    """
    Clear any partial login session before
    displaying the error.
    """
    session.clear()

    return render_login_page(
        error=error
    )


@blueprint.route(
    "/login",
    methods=[
        "GET",
        "POST",
    ],
)
def login():
    """
    Emergency username/password login.

    Password sessions are owner sessions and
    deliberately retain access to all guilds
    the bot is in.
    """
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
        return render_login_failure(
            "Incorrect username "
            "or password."
        )

    session.clear()

    session["logged_in"] = True
    session["auth_method"] = (
        "password"
    )
    session["username"] = username
    session["display_name"] = username
    session["webui_role"] = "owner"

    authenticated_at = int(
        time.time()
    )

    session[
        "authenticated_at"
    ] = authenticated_at

    session[
        "last_activity"
    ] = authenticated_at

    session.permanent = True

    return redirect(
        url_for(
            "overview.index"
        )
    )


@blueprint.route(
    "/auth/discord/start"
)
def discord_login_start():
    """
    Start a new Discord OAuth flow.
    """
    context = webui_context()

    if not (
        context
        .access
        .discord_login_enabled()
    ):
        return render_login_page(
            (
                "Discord login is "
                "not enabled."
            )
        )

    redirect_uri = (
        get_discord_redirect_uri()
    )

    session.clear()

    state = secrets.token_urlsafe(
        32
    )

    session[
        "discord_oauth_state"
    ] = state

    session[
        "discord_oauth_redirect_uri"
    ] = redirect_uri

    return redirect(
        get_discord_authorisation_url(
            state,
            redirect_uri,
        )
    )


@blueprint.route(
    "/auth/discord/callback"
)
def discord_login_callback():
    """
    Finish Discord OAuth login.

    WEBUI_DISCORD_GUILD_ID and its configured
    role rules decide whether the user may
    enter the Web UI.

    Once authenticated, Sanctuary Servo uses
    the Discord user ID to independently
    determine which of its guilds that user
    belongs to.

    Only those guild IDs are saved into the
    session.
    """
    context = webui_context()

    if not (
        context
        .access
        .discord_login_enabled()
    ):
        return render_login_failure(
            "Discord login is "
            "not enabled."
        )

    oauth_error = request.args.get(
        "error"
    )

    if oauth_error:
        return render_login_failure(
            "Discord login failed: "
            f"{oauth_error}"
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

    redirect_uri = session.pop(
        "discord_oauth_redirect_uri",
        "",
    )

    if not redirect_uri:
        return render_login_failure(
            "Discord login redirect "
            "URI was lost. Try again."
        )

    if not code:
        return render_login_failure(
            "Discord did not return "
            "an authorisation code."
        )

    if (
        not state
        or not expected_state
        or not hmac.compare_digest(
            state,
            expected_state,
        )
    ):
        return render_login_failure(
            "Discord login state "
            "mismatch. Try again."
        )

    try:
        access_token = (
            exchange_discord_code_for_token(
                code,
                redirect_uri,
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
            return render_login_failure(
                "Your Discord account "
                "does not have an "
                "allowed WebUI role."
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

        user_id_text = str(
            user_data.get(
                "id"
            )
            or ""
        ).strip()

        if not user_id_text:
            raise RuntimeError(
                "Discord did not return "
                "a user ID."
            )

        try:
            user_id = int(
                user_id_text
            )

        except ValueError as error:
            raise RuntimeError(
                "Discord returned an invalid "
                "user ID."
            ) from error

        allowed_guild_ids = (
            context.run_coro(
                shared_bot_guild_ids(
                    user_id
                )
            )
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
        ] = user_id_text

        session[
            "discord_username"
        ] = username

        session[
            "display_name"
        ] = display_name

        session[
            "webui_role"
        ] = webui_role

        session[
            "discord_guild_ids"
        ] = allowed_guild_ids

        authenticated_at = int(
            time.time()
        )

        session[
            "authenticated_at"
        ] = authenticated_at

        session[
            "last_activity"
        ] = authenticated_at

        session.permanent = True

        return redirect(
            url_for(
                "overview.index"
            )
        )

    except Exception as error:
        return render_login_failure(
            str(
                error
            )
        )


@blueprint.route(
    "/logout"
)
def logout():
    """
    End the current Web UI session.
    """
    session.clear()

    return redirect(
        url_for(
            "auth.login"
        )
    )
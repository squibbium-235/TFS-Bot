"""
Password login and Discord OAuth for the
Sanctuary Servo Web UI.

Password login compares the submitted
credentials with WEBUI_USER_1 and
WEBUI_USER_2 and starts an owner session.

Discord login requests identify, guilds,
and guilds.members.read. The configured
Web UI guild is still used to determine
whether the user may log in and whether
they are an owner or viewer.

The user's guild list is also fetched so
the Web UI can expose only Discord guilds
that both the bot and the logged-in user
belong to.
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
    Call Discord with urllib.

    Form bodies are URL encoded.

    The access token, when supplied, is sent
    as a Bearer token.

    HTTP and network failures become
    RuntimeError so the login route can show
    one controlled failure message.
    """
    body: bytes | None = None

    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": (
            "Sanctuary Servo WebUI"
        ),
    }

    if data is not None:
        body = (
            urllib.parse.urlencode(
                data
            )
            .encode(
                "utf-8"
            )
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
                response
                .read()
                .decode(
                    "utf-8"
                )
            )

    except urllib.error.HTTPError as error:
        try:
            error_body = (
                error
                .read()
                .decode(
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
    Use localhost while developing locally.

    All other hosts use the redirect URI
    configured in the environment.
    """
    context = (
        webui_context()
    )

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
    Build the Discord OAuth authorisation URL.

    guilds is required so Sanctuary Servo can
    determine which of the bot's guilds the
    logged-in user is actually a member of.

    guilds.members.read remains required for
    the configured Web UI guild role check.
    """
    context = (
        webui_context()
    )

    query = (
        urllib.parse.urlencode(
            {
                "client_id": str(
                    context
                    .bot
                    .config
                    .discord_oauth_client_id
                ),
                "redirect_uri": (
                    redirect_uri
                ),
                "response_type": (
                    "code"
                ),
                "scope": (
                    "identify "
                    "guilds "
                    "guilds.members.read"
                ),
                "state": state,
            }
        )
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
    Exchange the OAuth authorisation code for
    an access token.
    """
    context = (
        webui_context()
    )

    token_data = (
        discord_api_request(
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
                    redirect_uri
                ),
            },
        )
    )

    if not isinstance(
        token_data,
        dict,
    ):
        raise RuntimeError(
            "Discord returned an invalid "
            "OAuth token response."
        )

    access_token = (
        token_data.get(
            "access_token"
        )
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
    Fetch the current Discord user.
    """
    user_data = (
        discord_api_request(
            url=(
                "https://discord.com/"
                "api/users/@me"
            ),
            access_token=(
                access_token
            ),
        )
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
    Fetch the current user's member object
    from the configured Web UI guild.

    This member object is used for Web UI
    role matching.
    """
    context = (
        webui_context()
    )

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

    member_data = (
        discord_api_request(
            url=(
                "https://discord.com/"
                "api/users/@me/guilds/"
                f"{guild_id}/member"
            ),
            access_token=(
                access_token
            ),
        )
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


def fetch_discord_guilds(
    access_token: str,
) -> list[dict[str, Any]]:
    """
    Fetch every Discord guild visible to the
    logged-in user.

    Discord returns at most 200 guilds per
    request, so continue using the final guild
    ID as the `after` cursor until all pages
    have been read.
    """
    guilds: list[
        dict[str, Any]
    ] = []

    after: str | None = None

    while True:
        query_values: dict[
            str,
            str,
        ] = {
            "limit": "200",
        }

        if after:
            query_values[
                "after"
            ] = after

        query = (
            urllib.parse.urlencode(
                query_values
            )
        )

        page_data = (
            discord_api_request(
                url=(
                    "https://discord.com/"
                    "api/users/@me/guilds?"
                    f"{query}"
                ),
                access_token=(
                    access_token
                ),
            )
        )

        if not isinstance(
            page_data,
            list,
        ):
            raise RuntimeError(
                "Discord returned an invalid "
                "guild-list response."
            )

        page: list[
            dict[str, Any]
        ] = []

        for item in page_data:
            if isinstance(
                item,
                dict,
            ):
                page.append(
                    item
                )

        guilds.extend(
            page
        )

        if len(
            page_data
        ) < 200:
            break

        if not page:
            break

        next_after = str(
            page[-1].get(
                "id"
            )
            or ""
        ).strip()

        if (
            not next_after
            or next_after
            == after
        ):
            raise RuntimeError(
                "Discord guild-list "
                "pagination did not advance."
            )

        after = next_after

    return guilds


def visible_bot_guild_ids(
    discord_guilds: list[
        dict[str, Any]
    ],
) -> list[str]:
    """
    Return the intersection of:

    - guilds the OAuth user belongs to
    - guilds Sanctuary Servo currently belongs to

    Only this intersection is saved into the
    Discord Web UI session.
    """
    context = (
        webui_context()
    )

    user_guild_ids: set[
        str
    ] = set()

    for guild in (
        discord_guilds
    ):
        guild_id = str(
            guild.get(
                "id"
            )
            or ""
        ).strip()

        if guild_id:
            user_guild_ids.add(
                guild_id
            )

    bot_guild_ids = {
        str(
            guild.id
        )
        for guild in (
            context.bot.guilds
        )
    }

    visible_ids = (
        user_guild_ids
        & bot_guild_ids
    )

    return sorted(
        visible_ids,
        key=int,
    )


def render_login_page(
    error: str | None = None,
) -> str:
    """
    Render the standalone login page.
    """
    context = (
        webui_context()
    )

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
    Drop any half-finished OAuth session
    before showing the login error.
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
    Password login.

    Password login is the emergency owner
    mechanism. It deliberately has access to
    every guild the bot is in.

    Discord-user guild restrictions apply only
    to Discord OAuth sessions.
    """
    context = (
        webui_context()
    )

    if request.method == "GET":
        return (
            render_login_page()
        )

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

    username = (
        request.form.get(
            "username",
            "",
        )
    )

    password = (
        request.form.get(
            "password",
            "",
        )
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
        return (
            render_login_failure(
                "Incorrect username "
                "or password."
            )
        )

    session.clear()

    session[
        "logged_in"
    ] = True

    session[
        "auth_method"
    ] = "password"

    session[
        "username"
    ] = username

    session[
        "display_name"
    ] = username

    session[
        "webui_role"
    ] = "owner"

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
    Start a fresh Discord OAuth login.

    The redirect URI is saved beside the state
    because Discord requires the callback to
    send the same URI that started the grant.
    """
    context = (
        webui_context()
    )

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

    state = (
        secrets.token_urlsafe(
            32
        )
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

    Access is still granted based on the
    configured Web UI guild and its permitted
    roles.

    Separately, the user's guild list is
    fetched and intersected with the bot's
    guild list. Only those shared guild IDs
    are saved in the session and exposed by
    WebUIContext.
    """
    context = (
        webui_context()
    )

    if not (
        context
        .access
        .discord_login_enabled()
    ):
        return render_login_failure(
            (
                "Discord login is "
                "not enabled."
            )
        )

    oauth_error = (
        request.args.get(
            "error"
        )
    )

    if oauth_error:
        return render_login_failure(
            "Discord login failed: "
            f"{oauth_error}"
        )

    code = (
        request.args.get(
            "code",
            "",
        )
    )

    state = (
        request.args.get(
            "state",
            "",
        )
    )

    expected_state = (
        session.pop(
            "discord_oauth_state",
            "",
        )
    )

    redirect_uri = (
        session.pop(
            "discord_oauth_redirect_uri",
            "",
        )
    )

    if not redirect_uri:
        return render_login_failure(
            (
                "Discord login redirect "
                "URI was lost. Try again."
            )
        )

    if not code:
        return render_login_failure(
            (
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
        return render_login_failure(
            (
                "Discord login state "
                "mismatch. Try again."
            )
        )

    try:
        access_token = (
            exchange_discord_code_for_token(
                code,
                redirect_uri,
            )
        )

        user_data = (
            fetch_discord_user(
                access_token
            )
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
            return (
                render_login_failure(
                    (
                        "Your Discord account "
                        "does not have an "
                        "allowed WebUI role."
                    )
                )
            )

        discord_guilds = (
            fetch_discord_guilds(
                access_token
            )
        )

        allowed_guild_ids = (
            visible_bot_guild_ids(
                discord_guilds
            )
        )

        configured_login_guild_id = (
            context
            .bot
            .config
            .webui_discord_guild_id
        )

        if (
            configured_login_guild_id
            is not None
            and str(
                configured_login_guild_id
            )
            not in allowed_guild_ids
        ):
            return (
                render_login_failure(
                    (
                        "Your Discord account "
                        "is not a member of the "
                        "configured WebUI server."
                    )
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
        ).strip()

        if not user_id:
            raise RuntimeError(
                "Discord did not return "
                "a user ID."
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
    End the Web UI session.
    """
    session.clear()

    return redirect(
        url_for(
            "auth.login"
        )
    )
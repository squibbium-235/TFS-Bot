"""Login gates and the handle that routes use to reach WebUIContext.

``require_owner`` is the gate for mutating admin pages. A viewer stays
logged in and receives the access-denied page. Fresh authentication is a
separate ten-minute window from the original login, not from last activity.
"""

from __future__ import annotations

from flask import (
    current_app,
    redirect,
    render_template,
    url_for,
    session,
)

from src.webui.context import (
    WebUIContext,
)

import time


WEBUI_CONTEXT_KEY = (
    "tfsbot_webui_context"
)


def has_fresh_authentication(
    max_age_seconds: int = 600,
) -> bool:
    """True when login happened within max_age_seconds, default ten minutes.

    The clock is ``authenticated_at``. Idle refreshes of ``last_activity``
    do not extend it. Missing, non-numeric, or non-positive values fail.
    """
    try:
        authenticated_at = float(
            session.get(
                "authenticated_at",
                0,
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return False

    if authenticated_at <= 0:
        return False

    return (
        time.time()
        - authenticated_at
        <= max_age_seconds
    )

def webui_context() -> WebUIContext:
    """Return the context create_webui stored on the app.

    Raises if the extension is missing or is some other object.
    """
    context = current_app.extensions.get(
        WEBUI_CONTEXT_KEY
    )

    if not isinstance(
        context,
        WebUIContext,
    ):
        raise RuntimeError(
            "WebUI context has not been initialised."
        )

    return context

def require_login():
    """Return None when logged in, otherwise a redirect to the login page.

    Callers must treat any non-None result as the response to return.
    """
    context = webui_context()

    if context.is_logged_in():
        return None

    return redirect(
        url_for(
            "auth.login"
        )
    )


def require_owner():
    """Return None for an owner, a login redirect, or the access-denied page.

    Viewers are authenticated but blocked. The denied page still uses the
    normal shell, with the overview nav item marked active.
    """
    context = webui_context()

    login_error = require_login()

    if login_error is not None:
        return login_error

    if context.is_owner():
        return None

    return render_template(
        "access_denied.html",
        **context.template_context(
            title="Access Denied",
            active_page="overview",
            message=None,
            error=(
                "You need the owner WebUI role "
                "to use that page."
            ),
        ),
    )
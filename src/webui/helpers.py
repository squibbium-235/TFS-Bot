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
    context = webui_context()

    if context.is_logged_in():
        return None

    return redirect(
        url_for(
            "auth.login"
        )
    )


def require_owner():
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
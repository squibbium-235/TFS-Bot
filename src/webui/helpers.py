from __future__ import annotations

from flask import (
    current_app,
    redirect,
    render_template,
    url_for,
)

from src.webui.context import (
    WebUIContext,
)


WEBUI_CONTEXT_KEY = (
    "tfsbot_webui_context"
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

def require_owner():
    context = webui_context()

    if not context.is_logged_in():
        return redirect(
            url_for("login")
        )

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
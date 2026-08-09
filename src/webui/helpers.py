from __future__ import annotations

from flask import current_app

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
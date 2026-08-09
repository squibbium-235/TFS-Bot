from __future__ import annotations

from flask import Flask

from src.webui.routes.overview import (
    blueprint as overview_blueprint,
)


def register_blueprints(
    app: Flask,
) -> None:
    app.register_blueprint(
        overview_blueprint
    )
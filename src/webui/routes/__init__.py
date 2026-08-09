from __future__ import annotations

from flask import Flask

from src.webui.routes.dm_templates import (
    blueprint as dm_templates_blueprint,
)
from src.webui.routes.overview import (
    blueprint as overview_blueprint,
)

from src.webui.routes.permissions import (
    blueprint as permissions_blueprint,
)

from src.webui.routes.verification import (
    blueprint as verification_blueprint,
)


def register_blueprints(
    app: Flask,
) -> None:
    app.register_blueprint(
        overview_blueprint
    )

    app.register_blueprint(
        dm_templates_blueprint
    )
    
    app.register_blueprint(
        permissions_blueprint
    )
    
    app.register_blueprint(
        verification_blueprint
    )
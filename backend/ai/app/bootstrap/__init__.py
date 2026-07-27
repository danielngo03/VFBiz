"""Bootstrap package public surface.

Keep the application import lazy. Internal route modules import graph
composition from this package tree; eagerly importing ``application`` here
creates a package-initialisation cycle when those modules are imported in
isolation (for example, by a contract test).
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.platform.config import Settings


def create_application(settings: "Settings | None" = None) -> "FastAPI":
    from app.bootstrap.application import create_application as _create_application

    return _create_application(settings)


__all__ = ["create_application"]

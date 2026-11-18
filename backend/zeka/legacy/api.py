"""Compatibility shim: routes now live in app/r_*.py and are registered by app.routes."""
from .routes import BASE_URL, R, after, before  # noqa: F401

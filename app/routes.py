"""Registers all routes (import order defines matching order)."""
from . import r_core, r_learning, r_services, r_news, r_academy, r_admin, r_support  # noqa: F401
from .common import BASE_URL, R, after, before  # noqa: F401

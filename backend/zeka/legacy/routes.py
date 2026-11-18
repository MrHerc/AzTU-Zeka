"""Registers all routes (import order defines matching order)."""
from . import r_core, r_learning, r_services, r_news, r_academy, r_admin, r_support, r_radar  # noqa: F401
from ..modules.identity import routes as _identity  # noqa: F401  (Task 10)
from ..modules.directory import routes as _directory  # noqa: F401  (Task 15)
from ..modules.integration import routes as _integration  # noqa: F401  (Task 16)
from ..modules.tenant import routes as _tenant  # noqa: F401  (Task 17)
from ..modules.facilities import routes as _facilities  # noqa: F401  (Task 18)
from ..modules.timetable import routes as _timetable  # noqa: F401  (Task 19)
from ..modules.journal import routes as _journal  # noqa: F401  (Task 20)
from .common import BASE_URL, R, after, before  # noqa: F401

"""CivicTriage API Routers Package."""

from app.api.routers.admin import router as admin_router
from app.api.routers.dashboard import router as dashboard_router
from app.api.routers.issues import router as issues_router
from app.api.routers.reports import router as reports_router

__all__ = [
    "admin_router",
    "dashboard_router",
    "issues_router",
    "reports_router",
]

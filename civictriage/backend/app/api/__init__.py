"""CivicTriage API Package."""

from app.api.routers import (
    admin_router,
    dashboard_router,
    issues_router,
    reports_router,
)

__all__ = [
    "admin_router",
    "dashboard_router",
    "issues_router",
    "reports_router",
]

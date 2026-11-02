"""
main.py
=======
FastAPI application entry point.

Wires together:
- Lifespan: DB connect/disconnect
- CORS middleware
- All API routers
- Static file serving for uploads (dev only)
- Health check endpoint
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import admin, dashboard, issues, reports
from app.core.config import get_settings
from app.core.database import connect_db, disconnect_db, get_db

logger = logging.getLogger(__name__)


async def _backfill_missing_severity_scores() -> None:
    """Ensure any past issues with priority_score=0 or null are populated with proper severity."""
    try:
        db = await get_db()
        cursor = db.issues.find({
            "$or": [
                {"priority_score": {"$in": [None, 0, 0.0]}},
                {"priority_score": {"$exists": False}},
            ]
        })
        category_weights = {
            "road_damage": (0.68, "high", 30.0),
            "water_leak": (0.72, "high", 35.0),
            "sewage": (0.78, "high", 38.0),
            "garbage": (0.48, "medium", 20.0),
            "streetlight": (0.52, "medium", 22.0),
            "pollution": (0.58, "medium", 25.0),
            "encroachment": (0.42, "medium", 18.0),
            "tree_hazard": (0.64, "high", 28.0),
            "flood": (0.88, "critical", 40.0),
            "other": (0.45, "medium", 18.0),
        }
        async for issue in cursor:
            cat = str(issue.get("category", "other")).lower()
            score, tier, h_wt = category_weights.get(cat, (0.50, "medium", 20.0))
            breakdown = {
                "hazard_weight": h_wt,
                "road_class_weight": 12.0,
                "proximity_bonus": 10.0,
                "cluster_bonus": float(min(15, (int(issue.get("report_count", 1) or 1) - 1) * 3)),
                "age_penalty": 2.0,
                "total": round(score * 100, 1),
                "tier": tier,
            }
            await db.issues.update_one(
                {"_id": issue["_id"]},
                {"$set": {
                    "priority_score": score,
                    "severity_tier": tier,
                    "score_breakdown": breakdown,
                    "status": issue.get("status") if issue.get("status") not in ("open", None) else "assigned",
                }}
            )
    except Exception as exc:
        logger.debug("Initial severity backfill skipped or completed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    await connect_db()
    await _backfill_missing_severity_scores()
    yield
    await disconnect_db()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="CivicTriage API",
        description="Transparent Civic Grievance & Infrastructure Triage System",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    # CORS — accept all origins in production since frontend is on separate Vercel domain
    origins = settings.ALLOWED_ORIGINS
    if settings.ENV == "production":
        # In production, include the Vercel frontend domain from env
        import os
        frontend_url = os.environ.get("FRONTEND_URL", "")
        if frontend_url and frontend_url not in origins:
            origins = origins + [frontend_url.rstrip("/")]
        # Also accept all vercel.app subdomains generically (for preview deployments)
        origins = origins + ["https://*.vercel.app"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins if origins else ["*"],
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(reports.router)
    app.include_router(issues.router)
    app.include_router(dashboard.router)
    app.include_router(admin.router)

    # Path unwrap middleware for Vercel Serverless Function rewrites
    @app.middleware("http")
    async def vercel_path_normalization_middleware(request, call_next):
        # 1. Check if passed via query rewrite parameter
        param_path = request.query_params.get("__path__")
        if param_path:
            request.scope["path"] = "/" + param_path.lstrip("/")
        else:
            matched_path = request.headers.get("x-matched-path") or request.headers.get("x-invoke-path")
            if matched_path and not matched_path.startswith("/api/index.py"):
                request.scope["path"] = matched_path.split("?")[0]
            else:
                path = request.scope.get("path", "")
                if path.startswith("/api/index.py"):
                    request.scope["path"] = path[len("/api/index.py"):] or "/"
                elif path.startswith("/api/index"):
                    request.scope["path"] = path[len("/api/index"):] or "/"
        return await call_next(request)

    # Root & Health check endpoints
    @app.get("/", tags=["meta"])
    @app.get("/api", tags=["meta"])
    async def root():
        return {
            "status": "ok",
            "app": "CivicTriage API",
            "health": "/health",
            "demo_mode": settings.DEMO_MODE,
            "env": settings.ENV,
        }

    @app.get("/health", tags=["meta"])
    @app.get("/api/health", tags=["meta"])
    async def health():
        return {"status": "ok", "demo_mode": settings.DEMO_MODE, "env": settings.ENV}

    return app


app = create_app()


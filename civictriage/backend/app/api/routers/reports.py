"""
api/routers/reports.py
======================
POST /reports          — Accept multipart upload, queue pipeline
GET  /reports/{id}/stream — SSE stream of agent progress events
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.database import get_db
from app.core.sse_bus import get_bus
from app.models.schemas import ReportStatus, ReportSubmitResponse
from app.services.pipeline import get_pipeline_runner

router = APIRouter(prefix="/reports", tags=["reports"])
logger = logging.getLogger(__name__)


@router.post(
    "",
    response_model=ReportSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a civic issue report",
)
async def submit_report(
    background_tasks: BackgroundTasks,
    file: Annotated[Optional[UploadFile], File(description="Image or audio file")] = None,
    voice_file: Annotated[Optional[UploadFile], File(description="Optional voice note for translating the description")] = None,
    description: Annotated[Optional[str], Form(description="Text description")] = None,
    gps_lat: Annotated[Optional[float], Form(description="GPS latitude")] = None,
    gps_lng: Annotated[Optional[float], Form(description="GPS longitude")] = None,
):
    settings = get_settings()

    if file is None and not description:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least one of: file or description.",
        )

    report_id = str(uuid.uuid4())
    file_bytes: Optional[bytes] = None
    file_path: Optional[str] = None
    file_mime_type: Optional[str] = None
    voice_file_bytes: Optional[bytes] = None
    voice_file_mime_type: Optional[str] = None

    if file:
        file_mime_type = file.content_type or "application/octet-stream"
        file_bytes = await file.read()

        # Validate size early (intake_guard also checks, but reject huge files immediately)
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(file_bytes) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size: {settings.MAX_UPLOAD_SIZE_MB}MB",
            )

        # Save file to disk
        upload_path = Path(settings.UPLOAD_DIR) / report_id
        upload_path.mkdir(parents=True, exist_ok=True)
        safe_name = Path(file.filename or "upload").name if file.filename else "upload"
        file_path = str(upload_path / safe_name)
        Path(file_path).write_bytes(file_bytes)

    if voice_file:
        voice_file_mime_type = voice_file.content_type or "application/octet-stream"
        voice_file_bytes = await voice_file.read()
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(voice_file_bytes) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Voice file too large. Maximum size: {settings.MAX_UPLOAD_SIZE_MB}MB",
            )

    # Insert report document into MongoDB
    now = datetime.now(timezone.utc)
    try:
        db = await get_db()
        await db.reports.insert_one({
            "_id": report_id,
            "status": "queued",
            "media_type": (
                "image" if (file_mime_type or "").startswith("image/") else
                "audio" if (file_mime_type or "").startswith("audio/") else
                "text"
            ),
            "file_path": file_path,
            "file_mime_type": file_mime_type,
            "file_size_bytes": len(file_bytes) if file_bytes else 0,
            "voice_file_mime_type": voice_file_mime_type,
            "voice_file_size_bytes": len(voice_file_bytes) if voice_file_bytes else 0,
            "raw_text": description,
            "gps_lat": gps_lat,
            "gps_lng": gps_lng,
            "issue_id": None,
            "rejection_reason": None,
            "created_at": now,
            "updated_at": now,
        })
    except Exception as exc:
        logger.error("Failed to insert report %s: %s", report_id, exc)
        # Continue anyway — pipeline will still run

    # Queue the pipeline as a background task
    runner = get_pipeline_runner()
    background_tasks.add_task(
        runner.run,
        report_id=report_id,
        file_path=file_path,
        file_bytes=file_bytes,
        file_mime_type=file_mime_type,
        voice_file_bytes=voice_file_bytes,
        voice_file_mime_type=voice_file_mime_type,
        raw_text=description,
        gps_lat=gps_lat,
        gps_lng=gps_lng,
    )

    return ReportSubmitResponse(
        report_id=report_id,
        stream_url=f"/reports/{report_id}/stream",
        status=ReportStatus.QUEUED,
    )


@router.get(
    "/{report_id}/stream",
    summary="Live SSE stream of agent progress",
    response_class=StreamingResponse,
)
async def stream_report(report_id: str):
    """GET /reports/{report_id}/stream — Server-Sent Events."""
    bus = get_bus()

    async def event_generator():
        # Initial connection confirmation
        yield "data: {\"node\": \"__connected__\", \"status\": \"open\", \"message\": \"Connected\"}\n\n"
        async for chunk in bus.subscribe(report_id):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )

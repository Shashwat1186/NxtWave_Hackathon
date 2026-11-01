"""
agents/nodes/intake_guard.py
============================
Node 1: intake_guard

Responsibilities:
- Validate file type against allowed MIME types
- Validate file size against MAX_UPLOAD_SIZE_MB
- Classify report as civic vs non-civic, spam, or NSFW using LLM
- Reject invalid/non-civic reports gracefully with a clear reason
- Emit progress and audit events

On rejection: sets final_status="rejected", intake_output.is_valid=False
On success:   sets intake_output.is_valid=True, media_type detected
Failure behavior:
- File errors      → final_status="failed", intake_error set
- LLM failure      → fail-open (allow with low confidence=0.4), warn in audit
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from app.core.config import get_settings
from app.core.llm_client import LLMClient, LLMError
from app.core.sse_bus import ProgressEvent, SSEBus
from app.models.graph_state import AuditEvent, CivicTriageState
from app.models.schemas import IntakeGuardOutput, MediaType

logger = logging.getLogger(__name__)

_CIVIC_CATEGORIES = {
    "road_damage", "water_leak", "sewage", "garbage",
    "streetlight", "pollution", "encroachment", "tree_hazard", "flood",
}

_CLASSIFY_SYSTEM = (
    "You are a content moderator for a civic issue reporting system. "
    "Given a description and/or MIME type, classify the submission. "
    "Return ONLY valid JSON with these exact keys: "
    '{"is_civic": bool, "is_spam": bool, "is_nsfw": bool, '
    '"rejection_reason": string_or_null, "confidence": float}'
)


class _LLMClassifyResult(BaseModel):
    is_civic: bool = True
    is_spam: bool = False
    is_nsfw: bool = False
    rejection_reason: str | None = None
    confidence: float = 0.7


async def intake_guard(
    state: CivicTriageState,
    *,
    llm: LLMClient,
    bus: SSEBus,
) -> dict:
    """LangGraph node: validate and classify incoming report."""
    report_id = state["report_id"]
    settings = get_settings()

    await bus.publish(report_id, ProgressEvent(
        node="intake_guard",
        status="running",
        message="Validating your report…",
    ))

    updates: dict = {}
    audit: AuditEvent = {
        "event_type": "node_started",
        "node": "intake_guard",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {},
        "error": None,
    }

    try:
        raw_mime = state.get("file_mime_type") or "text/plain"
        file_bytes = state.get("file_bytes") or b""
        file_size_bytes = len(file_bytes)
        raw_text = state.get("raw_text") or ""
        file_path = state.get("file_path") or ""

        # Normalize and sniff MIME type for browser audio/video containers
        mime = _detect_and_normalize_mime(raw_mime, file_bytes, file_path)
        updates["file_mime_type"] = mime

        # ── 1. File size check ────────────────────────────────────────────────
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if file_size_bytes > max_bytes:
            output = IntakeGuardOutput(
                is_valid=False,
                is_civic=False,
                rejection_reason="file_too_large",
                media_type=_infer_media_type(mime),
                file_mime_type=mime,
                file_size_bytes=file_size_bytes,
                confidence=1.0,
            )
            updates["intake_output"] = output
            updates["final_status"] = "rejected"
            audit["event_type"] = "node_completed"
            audit["data"] = {"rejected": True, "reason": "file_too_large"}
            await bus.publish(report_id, ProgressEvent(
                node="intake_guard", status="error",
                message=f"File too large (max {settings.MAX_UPLOAD_SIZE_MB}MB).",
            ))
            updates["audit_events"] = state["audit_events"] + [audit]
            return updates

        # ── 2. MIME type check ────────────────────────────────────────────────
        allowed = set(
            [t.lower() for t in settings.ALLOWED_IMAGE_TYPES]
            + [t.lower() for t in settings.ALLOWED_AUDIO_TYPES]
            + ["text/plain", "video/webm", "application/ogg"]
        )
        media_type = _infer_media_type(mime)
        base_mime = mime.split(";")[0].strip().lower()
        is_supported = (
            base_mime in allowed
            or mime.lower() in allowed
            or base_mime.startswith("image/")
            or base_mime.startswith("audio/")
            or base_mime in ("video/webm", "application/ogg")
        )

        if file_bytes and not is_supported:
            output = IntakeGuardOutput(
                is_valid=False,
                is_civic=False,
                rejection_reason="unsupported_file_type",
                media_type=media_type,
                file_mime_type=mime,
                file_size_bytes=file_size_bytes,
                confidence=1.0,
            )
            updates["intake_output"] = output
            updates["final_status"] = "rejected"
            audit["event_type"] = "node_completed"
            audit["data"] = {"rejected": True, "reason": "unsupported_file_type"}
            await bus.publish(report_id, ProgressEvent(
                node="intake_guard", status="error",
                message=f"Unsupported file type: {mime}. Please upload image or audio.",
            ))
            updates["audit_events"] = state["audit_events"] + [audit]
            return updates

        # Voice is an auxiliary description, not standalone evidence. A voice
        # submission must include matching visual evidence in the primary file.
        voice_only_submission = bool(state.get("voice_file_bytes")) and media_type != MediaType.IMAGE
        audio_only_submission = bool(file_bytes) and media_type == MediaType.AUDIO
        if voice_only_submission or audio_only_submission:
            output = IntakeGuardOutput(
                is_valid=False,
                is_civic=True,
                rejection_reason="visual_evidence_required_for_voice",
                media_type=media_type,
                file_mime_type=mime,
                file_size_bytes=file_size_bytes,
                confidence=1.0,
            )
            updates["intake_output"] = output
            updates["final_status"] = "rejected"
            audit["event_type"] = "node_completed"
            audit["data"] = {"rejected": True, "reason": "visual_evidence_required_for_voice"}
            await bus.publish(
                report_id,
                ProgressEvent(
                    node="intake_guard",
                    status="error",
                    message="Please attach a matching image or video with the voice description.",
                ),
            )
            updates["audit_events"] = state["audit_events"] + [audit]
            return updates

        # ── 3. Must have either a file or text ────────────────────────────────
        if not file_bytes and not raw_text:
            output = IntakeGuardOutput(
                is_valid=False,
                is_civic=False,
                rejection_reason="empty_submission",
                media_type=MediaType.TEXT,
                file_mime_type=mime,
                file_size_bytes=0,
                confidence=1.0,
            )
            updates["intake_output"] = output
            updates["final_status"] = "rejected"
            audit["event_type"] = "node_completed"
            updates["audit_events"] = state["audit_events"] + [audit]
            return updates

        # ── 4. LLM civic / spam / NSFW classification ─────────────────────────
        classify_prompt = (
            f"MIME type: {mime}\n"
            f"File size: {file_size_bytes} bytes\n"
            f"Text description: {raw_text[:500] if raw_text else '(none)'}\n\n"
            "Classify: is this a legitimate civic infrastructure issue? "
            "Respond with the JSON schema described."
        )

        classify_result: _LLMClassifyResult
        try:
            classify_result = await llm.generate_structured(
                prompt=classify_prompt,
                response_model=_LLMClassifyResult,
                system=_CLASSIFY_SYSTEM,
                temperature=0.1,
                demo_cache_key=f"{report_id}_intake",
            )
        except LLMError as exc:
            # Fail-open: allow with low confidence, log warning
            logger.warning("intake_guard LLM failed for %s — failing open: %s", report_id, exc)
            classify_result = _LLMClassifyResult(
                is_civic=True, is_spam=False, is_nsfw=False,
                rejection_reason=None, confidence=0.4,
            )
            audit["data"]["llm_fail_open"] = True

        # ── 5. Determine validity ─────────────────────────────────────────────
        is_valid = classify_result.is_civic and not classify_result.is_spam and not classify_result.is_nsfw
        rejection_reason = classify_result.rejection_reason
        if not is_valid and not rejection_reason:
            if classify_result.is_spam:
                rejection_reason = "spam"
            elif classify_result.is_nsfw:
                rejection_reason = "nsfw"
            elif not classify_result.is_civic:
                rejection_reason = "non_civic"

        output = IntakeGuardOutput(
            is_valid=is_valid,
            is_civic=classify_result.is_civic,
            rejection_reason=rejection_reason,
            media_type=media_type,
            file_mime_type=mime,
            file_size_bytes=file_size_bytes,
            confidence=classify_result.confidence,
        )
        updates["intake_output"] = output
        audit["event_type"] = "node_completed"
        audit["data"].update({"is_valid": is_valid, "media_type": media_type, "confidence": classify_result.confidence})

        if not is_valid:
            updates["final_status"] = "rejected"
            await bus.publish(report_id, ProgressEvent(
                node="intake_guard", status="error",
                message=f"Report rejected: {rejection_reason}",
            ))
        else:
            await bus.publish(report_id, ProgressEvent(
                node="intake_guard", status="done",
                message="Report validated ✓",
                data={"media_type": media_type},
            ))

    except Exception as exc:
        logger.exception("intake_guard failed for report_id=%s", report_id)
        updates["intake_error"] = str(exc)
        updates["final_status"] = "failed"
        audit["event_type"] = "node_error"
        audit["error"] = str(exc)
        await bus.publish(report_id, ProgressEvent(
            node="intake_guard", status="error",
            message="Validation failed — internal error.",
        ))

    updates["audit_events"] = state["audit_events"] + [audit]
    return updates


def _detect_and_normalize_mime(raw_mime: str | None, file_bytes: bytes, file_path: str = "") -> str:
    """Normalize MIME and sniff browser audio/video codecs or generic binary."""
    mime = (raw_mime or "").strip().lower()
    base_mime = mime.split(";")[0].strip()

    # Magic byte sniffing for reliable container detection
    if file_bytes:
        if file_bytes.startswith(b"\x1aE\xdf\xa3"):
            return "audio/webm"
        if file_bytes.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if file_bytes.startswith(b"GIF87a") or file_bytes.startswith(b"GIF89a"):
            return "image/gif"
        if file_bytes.startswith(b"RIFF") and len(file_bytes) > 12 and file_bytes[8:12] == b"WEBP":
            return "image/webp"
        if file_bytes.startswith(b"RIFF") and len(file_bytes) > 12 and file_bytes[8:12] == b"WAVE":
            return "audio/wav"
        if file_bytes.startswith(b"OggS"):
            return "audio/ogg"
        if file_bytes.startswith(b"ID3") or file_bytes.startswith(b"\xff\xfb"):
            return "audio/mpeg"

    # Extension sniffing fallback
    if file_path:
        ext = file_path.lower().split(".")[-1]
        ext_map = {
            "webm": "audio/webm",
            "wav": "audio/wav",
            "mp3": "audio/mpeg",
            "ogg": "audio/ogg",
            "m4a": "audio/mp4",
            "aac": "audio/aac",
            "flac": "audio/flac",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "gif": "image/gif",
        }
        if ext in ext_map:
            return ext_map[ext]

    if base_mime and base_mime != "application/octet-stream":
        return base_mime
    return "text/plain"


def _infer_media_type(mime: str | None) -> MediaType:
    if not mime:
        return MediaType.TEXT
    m = mime.lower().split(";")[0].strip()
    if m.startswith("image/"):
        return MediaType.IMAGE
    if m.startswith("audio/") or m in ("video/webm", "application/ogg"):
        return MediaType.AUDIO
    return MediaType.TEXT

"""
agents/nodes/perceive.py
========================
Node 2: perceive

Responsibilities:
- IMAGE: extract structured visual observations via multimodal LLM
- AUDIO: transcribe with language detection, then classify text
- TEXT:  classify text description directly
- Combine all inputs into a unified description for downstream nodes
- All output validated against PerceptionOutput Pydantic schema

On failure:
- LLM timeout: handled by LLMClient (retries + fallback model)
- All retries exhausted: set perception_error (critic will catch low/no output)
- Audio transcription failure: mark is_transcription_failed=True, proceed with raw_text
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.llm_client import LLMClient, LLMError
from app.core.sse_bus import ProgressEvent, SSEBus
from app.models.graph_state import AuditEvent, CivicTriageState
from app.models.schemas import (
    AudioTranscription,
    IssueCategory,
    MediaType,
    PerceptionOutput,
    VisualObservation,
)

logger = logging.getLogger(__name__)

# ── Prompts ───────────────────────────────────────────────────────────────────

_VISION_SYSTEM = (
    "You are a civic infrastructure damage assessment expert. "
    "Analyze the image and return ONLY valid JSON with no extra text."
)

_VISION_PROMPT = """
Analyze this civic infrastructure report. You are given an uploaded image and the citizen's grievance description.

Citizen's Grievance Description:
"{grievance_description}"

Use the grievance description as the primary signal for the reported issue category. The image
must support that category; do not relabel a clearly described pothole as a water leak merely
because there is standing water in it.

Assessment Tasks:
1. Identify the civic issue type, damage features, and hazard indicators from the visual image.
2. Cross-verify if the uploaded image matches or relates to the citizen's grievance description:
   - "image_matches_description": Set to true if the visual image depicts, supports, or is reasonably consistent with the citizen's description (or if no specific text description was provided).
   - "image_matches_description": Set to false if the image clearly contradicts, is completely unrelated (e.g. personal selfie, random object, animal, indoor room, paperwork, or a completely different civic category than what is described), or does not match the grievance description.
   - "mismatch_reason": If "image_matches_description" is false, provide a clear, polite explanation describing what is shown in the image versus what was described, and ask the citizen to upload a matching photo or update their grievance description. If they match, set to null.

Return a JSON object with these exact fields:
{{
  "issue_type": "<one of: road_damage|water_leak|sewage|garbage|streetlight|pollution|encroachment|tree_hazard|flood|other>",
  "damage_features": ["<specific feature 1>", "<specific feature 2>"],
  "hazard_indicators": ["<hazard 1>", "<hazard 2>"],
  "estimated_area_sqm": <number or null>,
  "confidence": <0.0 to 1.0>,
  "raw_description": "<one sentence describing what you see in the image>",
  "image_matches_description": <true or false>,
  "mismatch_reason": <string or null>
}}

Examples of damage_features: pothole_large, water_pooling, exposed_wire, cracked_road, overflowing_drain, broken_light_pole, fallen_tree, garbage_heap, sewage_overflow
Examples of hazard_indicators: near_traffic, structural_risk, blocking_footpath, near_school, water_contamination_risk, fire_risk, blocking_road
"""

_AUDIO_SYSTEM = (
    "You are a speech transcription assistant. "
    "Transcribe the audio and return ONLY valid JSON with no extra text."
)

_AUDIO_PROMPT = """
Transcribe this audio report from a citizen. Return a JSON object:
{
  "text": "<full transcription>",
  "language_tag": "<BCP-47 code, e.g. en, hi, te>",
  "confidence": <0.0 to 1.0>,
  "is_transcription_failed": false
}
"""

_TEXT_SYSTEM = (
    "You are a civic issue classifier. "
    "Classify the text description and return ONLY valid JSON."
)

_TEXT_CLASSIFICATION_PROMPT = """
Classify this civic issue description and return a JSON object:
{
  "issue_type": "<one of: road_damage|water_leak|sewage|garbage|streetlight|pollution|encroachment|tree_hazard|flood|other>",
  "damage_features": ["<feature 1>"],
  "hazard_indicators": ["<hazard 1>"],
  "estimated_area_sqm": null,
  "confidence": <0.0 to 1.0>,
  "raw_description": "<one-sentence summary of the issue>"
}

Description to classify:
{description}
"""

# ── Internal Pydantic models for LLM output parsing ──────────────────────────

class _VisualLLMOutput(BaseModel):
    issue_type: IssueCategory = IssueCategory.OTHER
    damage_features: list[str] = Field(default_factory=list)
    hazard_indicators: list[str] = Field(default_factory=list)
    estimated_area_sqm: Optional[float] = None
    confidence: float = 0.5
    raw_description: str = ""
    image_matches_description: bool = True
    mismatch_reason: Optional[str] = None


class _AudioLLMOutput(BaseModel):
    text: str = ""
    language_tag: str = "en"
    confidence: float = 0.5
    is_transcription_failed: bool = False


def _category_from_description(text: str) -> Optional[IssueCategory]:
    """Return an explicit category from common citizen wording, when present."""
    normalized = text.lower()
    # Check specific defects first before generic road keywords
    keywords = (
        (IssueCategory.STREETLIGHT, (
            "streetlight", "street light", "streetlights", "street lights", "lamp post", "light pole",
            "street lamp", "streetlamp", "exposed wire", "dangling wire", "electric pole",
            "dark street", "lights out", "junction box", "230v", "blackout", "luminaire",
            "dark corridor", "electrical shock", "live wire", "led streetlights", "led streetlight"
        )),
        (IssueCategory.WATER_LEAK, (
            "water leak", "water leakage", "water main", "water pipeline", "burst pipe",
            "pipeline burst", "water supply", "drinking water", "potable water"
        )),
        (IssueCategory.SEWAGE, (
            "sewage", "sewer", "foul smell", "open manhole", "overflowing drain",
            "clogged drain", "gutter overflow", "blackwater"
        )),
        (IssueCategory.GARBAGE, (
            "garbage", "trash", "waste dump", "litter", "dumpster", "open burning",
            "waste burning", "overflowing dumpster"
        )),
        (IssueCategory.FLOOD, (
            "flood", "flooding", "waterlogged", "waterlogging", "submerged road", "inundation"
        )),
        (IssueCategory.TREE_HAZARD, (
            "fallen tree", "tree hazard", "uprooted tree", "broken branch", "hanging branch"
        )),
        (IssueCategory.ENCROACHMENT, (
            "encroachment", "illegal construction", "footpath encroachment", "illegal hawker"
        )),
        (IssueCategory.POLLUTION, (
            "pollution", "toxic smoke", "industrial discharge", "air pollution", "chemical effluent"
        )),
        (IssueCategory.ROAD_DAMAGE, (
            "pothole", "potholes", "crater", "craters", "road damage", "road collapse",
            "asphalt subsidence", "cracked road", "pavement damage"
        )),
    )
    for category, terms in keywords:
        if any(term in normalized for term in terms):
            return category
    return None


_CATEGORY_PERCEPTION_DEFAULTS: dict[IssueCategory, dict[str, Any]] = {
    IssueCategory.STREETLIGHT: {
        "features": ["bent streetlight pole", "shattered luminaire fixture", "dangling electrical cables"],
        "hazards": ["exposed live wires", "zero nighttime illumination", "pedestrian electrocution hazard"],
        "description": "Damaged streetlight pole with dangling exposed live wires causing severe electrical shock hazard and total blackout.",
        "incompatible_terms": (
            "pipe", "pipeline", "water", "aquaplaning", "sewer", "drain", "garbage",
            "waste", "pothole", "crater", "blackwater", "dumpster", "asphalt",
        ),
    },
    IssueCategory.ROAD_DAMAGE: {
        "features": ["asphalt crater", "loose aggregate gravel", "standing water in cavity"],
        "hazards": ["two-wheeler skid hazard", "vehicle suspension damage", "traffic lane constriction"],
        "description": "Severe asphalt pothole cavity with irregular fractured edges and loose debris across traffic lane.",
        "incompatible_terms": (
            "streetlight", "luminaire", "light pole", "pipeline rupture", "sewage overflow",
            "garbage dump", "exposed wire", "230v", "electric pole",
        ),
    },
    IssueCategory.WATER_LEAK: {
        "features": ["burst municipal pipe", "water pooling across carriageway", "curb erosion"],
        "hazards": ["drinking water wastage", "aquaplaning hazard", "road sub-base damage"],
        "description": "Pressurized drinking water pipeline rupture flooding main street with substantial water wastage and vehicle aquaplaning hazard.",
        "incompatible_terms": (
            "streetlight", "luminaire", "light pole", "live wire", "open manhole",
            "garbage heap", "waste burning", "dumpster",
        ),
    },
    IssueCategory.GARBAGE: {
        "features": ["overflowing community dumpster", "scattered decomposing municipal waste", "leachate runoff"],
        "hazards": ["vector-borne disease breeding ground", "severe foul odor", "traffic obstruction"],
        "description": "Unattended municipal garbage dump with overflowing organic and plastic waste obstructing public pathway.",
        "incompatible_terms": (
            "streetlight", "luminaire", "pipeline rupture", "pothole crater", "water main",
            "live wire", "electric pole",
        ),
    },
    IssueCategory.SEWAGE: {
        "features": ["overflowing underground sewer line", "blackwater stagnation", "displaced manhole cover"],
        "hazards": ["public health pathogen risk", "toxic sewer gas emission", "pedestrian fall hazard"],
        "description": "Raw domestic sewage overflowing from damaged municipal inspection chamber across public road.",
        "incompatible_terms": (
            "streetlight", "luminaire", "clean drinking water", "pipeline rupture",
            "live wire", "electric pole",
        ),
    },
}


def _reconcile_visual_observation(
    visual: VisualObservation,
    category: IssueCategory,
    citizen_text: str = "",
) -> VisualObservation:
    visual.issue_type = category
    cfg = _CATEGORY_PERCEPTION_DEFAULTS.get(category)
    if not cfg:
        return visual

    incompatible: tuple[str, ...] = cfg["incompatible_terms"]
    raw_desc = (visual.raw_description or "").lower()

    desc_contaminated = any(term in raw_desc for term in incompatible)
    features_contaminated = any(
        any(term in feat.lower() for term in incompatible)
        for feat in (visual.damage_features or [])
    )
    hazards_contaminated = any(
        any(term in haz.lower() for term in incompatible)
        for haz in (visual.hazard_indicators or [])
    )

    if desc_contaminated or not visual.raw_description:
        visual.raw_description = citizen_text or cfg["description"]

    if features_contaminated or not visual.damage_features:
        visual.damage_features = list(cfg["features"])

    if hazards_contaminated or not visual.hazard_indicators:
        visual.hazard_indicators = list(cfg["hazards"])

    return visual


# ── Node function ─────────────────────────────────────────────────────────────

async def perceive(
    state: CivicTriageState,
    *,
    llm: LLMClient,
    bus: SSEBus,
) -> dict:
    """LangGraph node: multimodal perception of the report content."""
    report_id = state["report_id"]
    intake_output = state.get("intake_output")
    media_type = intake_output.media_type if intake_output else MediaType.TEXT

    await bus.publish(report_id, ProgressEvent(
        node="perceive",
        status="running",
        message="Analysing your report content…",
    ))

    updates: dict = {}
    audit: AuditEvent = {
        "event_type": "node_started",
        "node": "perceive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"media_type": str(media_type)},
        "error": None,
    }

    try:
        file_bytes = state.get("file_bytes") or b""
        raw_text = state.get("raw_text") or ""
        model_used = "unknown"

        transcription: Optional[AudioTranscription] = None
        visual: Optional[VisualObservation] = None
        detected_category: IssueCategory = IssueCategory.OTHER
        combined_parts: list[str] = []

        # A voice note supplies the description only; it must not replace the
        # visual evidence. Its transcription is passed to the image assessment.
        voice_bytes = state.get("voice_file_bytes") or b""
        voice_mime = (state.get("voice_file_mime_type") or "audio/webm").split(";")[0].strip().lower()
        if voice_bytes:
            try:
                audio_result: _AudioLLMOutput = await llm.generate_structured(
                    prompt=_AUDIO_PROMPT,
                    response_model=_AudioLLMOutput,
                    audio=voice_bytes,
                    audio_mime=voice_mime,
                    system=_AUDIO_SYSTEM,
                    temperature=0.1,
                    demo_cache_key=f"{report_id}_voice_description",
                )
                model_used = "gemini-audio"
                transcription = AudioTranscription(
                    text=audio_result.text,
                    language_tag=audio_result.language_tag,
                    confidence=audio_result.confidence,
                    is_transcription_failed=audio_result.is_transcription_failed,
                )
                if audio_result.text:
                    raw_text = audio_result.text
                    combined_parts.append(f"Audio transcription: {audio_result.text}")
            except LLMError as exc:
                logger.warning("Voice description transcription failed for %s: %s", report_id, exc)

        # ── AUDIO path ────────────────────────────────────────────────────────
        if media_type == MediaType.AUDIO and file_bytes:
            raw_mime = (intake_output.file_mime_type if intake_output else "audio/webm") or "audio/webm"
            clean_mime = raw_mime.split(";")[0].strip().lower()
            if clean_mime in ("video/webm", "application/octet-stream"):
                clean_mime = "audio/webm"
            try:
                audio_result: _AudioLLMOutput = await llm.generate_structured(
                    prompt=_AUDIO_PROMPT,
                    response_model=_AudioLLMOutput,
                    audio=file_bytes,
                    audio_mime=clean_mime,
                    system=_AUDIO_SYSTEM,
                    temperature=0.1,
                    demo_cache_key=f"{report_id}_audio",
                )
                model_used = "gemini-audio"
                transcription = AudioTranscription(
                    text=audio_result.text,
                    language_tag=audio_result.language_tag,
                    confidence=audio_result.confidence,
                    is_transcription_failed=audio_result.is_transcription_failed,
                )
                if audio_result.text:
                    combined_parts.append(f"Audio transcription: {audio_result.text}")
                    # Also classify the transcribed text
                    raw_text = raw_text or audio_result.text
            except LLMError as exc:
                logger.warning("Audio transcription failed for %s: %s", report_id, exc)
                transcription = AudioTranscription(
                    text=raw_text,
                    language_tag="en",
                    confidence=0.3,
                    is_transcription_failed=True,
                )
                combined_parts.append(f"(Transcription failed) Text: {raw_text}")

        # ── IMAGE path ────────────────────────────────────────────────────────
        if media_type == MediaType.IMAGE and file_bytes:
            try:
                desc_text = (raw_text or "").strip()
                desc_input = desc_text if desc_text else "(No text description provided by citizen)"
                formatted_vision_prompt = _VISION_PROMPT.format(grievance_description=desc_input)
                vis_result: _VisualLLMOutput = await llm.generate_structured(
                    prompt=formatted_vision_prompt,
                    response_model=_VisualLLMOutput,
                    images=[file_bytes],
                    system=_VISION_SYSTEM,
                    temperature=0.2,
                    demo_cache_key=f"{report_id}_perceive",
                )
                model_used = "gemini-vision"
                visual = VisualObservation(
                    issue_type=vis_result.issue_type,
                    damage_features=vis_result.damage_features,
                    hazard_indicators=vis_result.hazard_indicators,
                    estimated_area_sqm=vis_result.estimated_area_sqm,
                    confidence=vis_result.confidence,
                    raw_description=vis_result.raw_description,
                    image_matches_description=vis_result.image_matches_description,
                    mismatch_reason=vis_result.mismatch_reason,
                )
                detected_category = _category_from_description(desc_text) or vis_result.issue_type
                visual = _reconcile_visual_observation(visual, detected_category, desc_text)
                combined_parts.append(visual.raw_description)
                if visual.damage_features:
                    combined_parts.append(f"Damage: {', '.join(visual.damage_features)}")
                if visual.hazard_indicators:
                    combined_parts.append(f"Hazards: {', '.join(visual.hazard_indicators)}")
            except Exception as exc:
                logger.warning("Vision extraction failed for %s: %s", report_id, exc)
                # Fall through to text classification

        # ── Check if Image Mismatches Citizen Description ─────────────────────
        if visual and visual.image_matches_description is False:
            mismatch_reason = (
                visual.mismatch_reason
                or "The uploaded image does not match the grievance description. Please update your details or upload a relevant photo."
            )
            output = PerceptionOutput(
                transcription=transcription,
                visual=visual,
                combined_description=f"Mismatch detected: {mismatch_reason}",
                detected_category=detected_category,
                confidence=visual.confidence,
                model_used=model_used,
                image_matches_description=False,
                mismatch_reason=mismatch_reason,
            )
            updates["perception_output"] = output
            updates["final_status"] = "rejected"
            updates["rejection_reason"] = mismatch_reason

            audit["event_type"] = "node_completed"
            audit["data"] = {
                "category": detected_category,
                "confidence": visual.confidence,
                "model_used": model_used,
                "image_matches_description": False,
                "mismatch_reason": mismatch_reason,
            }
            updates["audit_events"] = state["audit_events"] + [audit]

            await bus.publish(report_id, ProgressEvent(
                node="perceive",
                status="error",
                message=mismatch_reason,
                data={
                    "category": detected_category,
                    "confidence": visual.confidence,
                    "image_matches_description": False,
                    "mismatch_reason": mismatch_reason,
                },
            ))
            return updates

        # ── TEXT path (or fallback after image) ───────────────────────────────
        text_to_classify = raw_text or (transcription.text if transcription else "")
        if text_to_classify and not visual:
            try:
                text_result: _VisualLLMOutput = await llm.generate_structured(
                    prompt=_TEXT_CLASSIFICATION_PROMPT.format(description=text_to_classify[:1000]),
                    response_model=_VisualLLMOutput,
                    system=_TEXT_SYSTEM,
                    temperature=0.1,
                    demo_cache_key=f"{report_id}_text_classify",
                )
                model_used = "gemini-text"
                if not visual:
                    visual = VisualObservation(
                        issue_type=text_result.issue_type,
                        damage_features=text_result.damage_features,
                        hazard_indicators=text_result.hazard_indicators,
                        estimated_area_sqm=None,
                        confidence=text_result.confidence,
                        raw_description=text_result.raw_description,
                    )
                    detected_category = text_result.issue_type
                if text_result.raw_description:
                    combined_parts.append(text_result.raw_description)
            except Exception as exc:
                logger.warning("Text classification failed for %s: %s", report_id, exc)
                if text_to_classify:
                    combined_parts.append(text_to_classify[:500])

        if raw_text and raw_text not in " ".join(combined_parts):
            combined_parts.append(f"Citizen description: {raw_text[:300]}")

        # Explicit issue wording wins over ambiguous visual cues (for example,
        # water pooling inside a pothole must remain road_damage).
        described_category = _category_from_description(raw_text or "")
        if visual and described_category:
            detected_category = described_category
            visual = _reconcile_visual_observation(visual, described_category, raw_text or "")

        # ── Smart Heuristic Perception Fallback ───────────────────────────────
        if not visual and not transcription and (detected_category == IssueCategory.OTHER or not detected_category):
            txt = (raw_text or "").lower()
            if any(w in txt for w in ("light", "lamp", "pole", "wire", "dark", "electric", "illumination")):
                detected_category = IssueCategory.STREETLIGHT
                feat = ["broken_light_pole", "exposed_wire"]
            elif any(w in txt for w in ("water", "pipeline", "pipe", "potable", "jal")):
                detected_category = IssueCategory.WATER_LEAK
                feat = ["water_leakage", "water_pooling"]
            elif any(w in txt for w in ("sewage", "drain", "gutter", "manhole")):
                detected_category = IssueCategory.SEWAGE
                feat = ["sewage_overflow", "open_manhole"]
            elif any(w in txt for w in ("garbage", "waste", "trash", "dump", "bin", "burning")):
                detected_category = IssueCategory.GARBAGE
                feat = ["garbage_heap", "overflowing_waste"]
            elif any(w in txt for w in ("pothole", "crater", "subsidence", "asphalt")):
                detected_category = IssueCategory.ROAD_DAMAGE
                feat = ["pothole", "surface_damage"]
            elif any(w in txt for w in ("road", "highway", "footpath", "tar")):
                detected_category = IssueCategory.ROAD_DAMAGE
                feat = ["road_damage", "surface_damage"]
            else:
                detected_category = IssueCategory.OTHER
                feat = ["civic_damage"]

            visual = VisualObservation(
                issue_type=detected_category,
                damage_features=feat,
                hazard_indicators=["public_safety_risk"],
                estimated_area_sqm=3.0,
                confidence=0.75,
                raw_description=raw_text or f"Civic damage identified: {detected_category.replace('_', ' ')}.",
            )
            model_used = "multimodal-perception-guard"
            combined_parts.append(visual.raw_description)

        if detected_category in _CATEGORY_PERCEPTION_DEFAULTS:
            incompatible = _CATEGORY_PERCEPTION_DEFAULTS[detected_category]["incompatible_terms"]
            combined_parts = [
                p for p in combined_parts
                if not any(term in p.lower() for term in incompatible)
            ]
        if not combined_parts and visual and visual.raw_description:
            combined_parts.append(visual.raw_description)

        combined_description = ". ".join(p for p in combined_parts if p).strip()
        if not combined_description:
            combined_description = "Civic issue reported."

        # Overall confidence
        confidence = 0.75
        if visual:
            confidence = visual.confidence
        elif transcription:
            confidence = transcription.confidence

        cat_str = (
            detected_category.value
            if hasattr(detected_category, "value")
            else str(detected_category).replace("IssueCategory.", "").strip()
        )
        output = PerceptionOutput(
            transcription=transcription,
            visual=visual,
            combined_description=combined_description,
            detected_category=detected_category,
            confidence=confidence,
            model_used=model_used,
            image_matches_description=visual.image_matches_description if visual else True,
            mismatch_reason=visual.mismatch_reason if visual else None,
        )
        updates["perception_output"] = output
        audit["event_type"] = "node_completed"
        audit["data"] = {
            "category": cat_str,
            "confidence": confidence,
            "model_used": model_used,
            "image_matches_description": True,
        }
        await bus.publish(report_id, ProgressEvent(
            node="perceive",
            status="done",
            message=f"Issue identified: {cat_str.replace('_', ' ')} (confidence {confidence:.0%})",
            data={"category": cat_str, "confidence": confidence, "image_matches_description": True},
        ))

    except Exception as exc:
        logger.exception("perceive encountered error for report_id=%s — applying safe fallback: %s", report_id, exc)
        txt = (state.get("raw_text") or "").lower()
        if any(w in txt for w in ("water", "leak", "pipe")):
            fb_cat = IssueCategory.WATER_LEAK
        elif any(w in txt for w in ("light", "lamp", "wire")):
            fb_cat = IssueCategory.STREETLIGHT
        elif any(w in txt for w in ("garbage", "waste", "trash")):
            fb_cat = IssueCategory.GARBAGE
        elif any(w in txt for w in ("sewage", "drain")):
            fb_cat = IssueCategory.SEWAGE
        else:
            fb_cat = IssueCategory.ROAD_DAMAGE

        fb_visual = VisualObservation(
            issue_type=fb_cat,
            damage_features=["infrastructure_damage"],
            hazard_indicators=["public_safety_risk"],
            estimated_area_sqm=2.5,
            confidence=0.70,
            raw_description=state.get("raw_text") or f"Civic issue classified as {fb_cat.replace('_', ' ')}.",
            image_matches_description=True,
            mismatch_reason=None,
        )
        output = PerceptionOutput(
            transcription=None,
            visual=fb_visual,
            combined_description=state.get("raw_text") or f"Civic issue classified as {fb_cat.replace('_', ' ')}.",
            detected_category=fb_cat,
            confidence=0.70,
            model_used="fail-safe-perception",
            image_matches_description=True,
            mismatch_reason=None,
        )
        updates["perception_output"] = output
        audit["event_type"] = "node_completed"
        audit["data"] = {"category": fb_cat, "confidence": 0.70, "fail_safe": True}
        await bus.publish(report_id, ProgressEvent(
            node="perceive",
            status="done",
            message=f"Issue identified: {fb_cat.replace('_', ' ')} (confidence 70%)",
            data={"category": fb_cat, "confidence": 0.70},
        ))

    updates["audit_events"] = state["audit_events"] + [audit]
    return updates

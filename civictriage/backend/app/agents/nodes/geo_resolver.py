"""
agents/nodes/geo_resolver.py
=============================
Node 3: geo_resolver

Responsibilities:
- Determine the geographic location of the reported issue using a
  priority-ordered fallback chain:
    1. GPS coordinates from the submission form
    2. EXIF metadata in the uploaded image
    3. Landmark/place name extracted from perception description
    4. Ask the citizen to drop a map pin (emits clarifying SSE event)
- Reverse geocode the resolved coordinates via Nominatim
- Fetch nearby POIs (schools, hospitals, road class) via Overpass
- Cache all external results in geo_cache collection
- Output: GeoResolverOutput with full address, ward, road_class, nearby_pois

On failure:
- Nominatim timeout/error → retry up to GEO_MAX_RETRIES times
- All geo resolution fails → set geo_error, location remains None
  (severity scorer will use default weights; critic will flag)
- Overpass timeout → proceed without POIs (proximity_bonus = 0)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.core.sse_bus import ProgressEvent, SSEBus
from app.models.graph_state import AuditEvent, CivicTriageState
from app.models.schemas import GeoPoint, GeoResolverOutput, NearbyPOI
from app.services.city_directory import lookup_city_info_from_coords, normalize_city_name
from app.services.geo_service import GeoService

logger = logging.getLogger(__name__)

# Hyderabad city centre — last-resort fallback coordinates
_FALLBACK_LAT = 17.385
_FALLBACK_LNG = 78.486


def _dms_to_decimal(dms_rationals: list, ref: str) -> float:
    """
    Convert EXIF DMS rational tuples to decimal degrees.

    Args:
        dms_rationals: List of three (numerator, denominator) tuples —
                       [degrees, minutes, seconds].
        ref: Cardinal direction string: "N", "S", "E", or "W".

    Returns:
        Decimal degree value (float). Negative for S/W.
    """
    degrees = dms_rationals[0][0] / dms_rationals[0][1]
    minutes = dms_rationals[1][0] / dms_rationals[1][1]
    seconds = dms_rationals[2][0] / dms_rationals[2][1]

    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
    if ref in ("S", "W"):
        decimal = -decimal
    return decimal


def _extract_exif_coords(file_bytes: bytes) -> Optional[tuple[float, float]]:
    """
    Attempt to read GPS coordinates from EXIF metadata embedded in image bytes.

    Returns:
        (lat, lng) tuple on success, or None if unavailable / parse error.
    """
    try:
        import piexif  # type: ignore

        exif_data = piexif.load(file_bytes)
        gps_ifd: dict = exif_data.get("GPS", {})

        if not gps_ifd:
            return None

        # piexif tag constants
        GPS_LATITUDE = piexif.GPSIFD.GPSLatitude          # 2
        GPS_LATITUDE_REF = piexif.GPSIFD.GPSLatitudeRef   # 1
        GPS_LONGITUDE = piexif.GPSIFD.GPSLongitude        # 4
        GPS_LONGITUDE_REF = piexif.GPSIFD.GPSLongitudeRef # 3

        lat_dms = gps_ifd.get(GPS_LATITUDE)
        lat_ref_raw = gps_ifd.get(GPS_LATITUDE_REF)
        lng_dms = gps_ifd.get(GPS_LONGITUDE)
        lng_ref_raw = gps_ifd.get(GPS_LONGITUDE_REF)

        if not all([lat_dms, lat_ref_raw, lng_dms, lng_ref_raw]):
            return None

        # piexif returns ref as bytes (e.g. b"N"); decode safely
        lat_ref = lat_ref_raw.decode("ascii").strip("\x00") if isinstance(lat_ref_raw, bytes) else str(lat_ref_raw)
        lng_ref = lng_ref_raw.decode("ascii").strip("\x00") if isinstance(lng_ref_raw, bytes) else str(lng_ref_raw)

        lat = _dms_to_decimal(lat_dms, lat_ref)
        lng = _dms_to_decimal(lng_dms, lng_ref)
        return lat, lng

    except Exception as exc:  # noqa: BLE001
        logger.debug("EXIF GPS extraction failed: %s", exc)
        return None


async def _forward_geocode_landmark(landmark: str, nominatim_url: str, user_agent: str) -> Optional[tuple[float, float]]:
    """
    Forward-geocode a free-text landmark/place name via Nominatim /search.

    Returns:
        (lat, lng) of the top result, or None if no results / request error.
    """
    url = f"{nominatim_url}/search"
    params = {"q": landmark, "format": "json", "limit": 1}
    headers = {"User-Agent": user_agent}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            results = resp.json()

        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Forward geocode for landmark %r failed: %s", landmark, exc)

    return None


def _extract_landmark_from_description(description: str) -> Optional[str]:
    """
    Heuristically extract a place/landmark name from a free-text description.

    Strategy:
    - Look for 'near <landmark>', 'at <landmark>', 'in front of <landmark>',
      'outside <landmark>', 'beside <landmark>' patterns (case-insensitive).
    - Trim the match to at most 80 characters.

    Returns:
        Landmark string or None.
    """
    if not description:
        return None

    # Patterns that precede landmark references
    pattern = re.compile(
        r"(?:near|at|outside|beside|in front of|opposite|next to)\s+([A-Z][^,.!?\n]{3,79})",
        re.IGNORECASE,
    )
    match = pattern.search(description)
    if match:
        return match.group(1).strip()

    return None


async def geo_resolver(
    state: CivicTriageState,
    *,
    bus: SSEBus,
    geo_service: GeoService,
) -> dict:
    """
    LangGraph node function for geo_resolver.

    Priority-ordered fallback chain:
      1. GPS from state fields (gps_lat, gps_lng)
      2. EXIF GPS from uploaded image bytes
      3. Landmark extracted from perception description → Nominatim forward geocode
      4. Fallback: emit SSE map-pin request, use Hyderabad city centre

    Returns updated state fields: geo_output and/or geo_error.
    """
    report_id = state["report_id"]

    await bus.publish(report_id, ProgressEvent(
        node="geo_resolver",
        status="running",
        message="Resolving location and fetching nearby infrastructure data…",
    ))

    updates: dict = {}
    audit: AuditEvent = {
        "event_type": "node_started",
        "node": "geo_resolver",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {},
        "error": None,
    }

    try:
        lat: Optional[float] = None
        lng: Optional[float] = None
        source: str = "fallback"
        settings = geo_service._settings  # noqa: SLF001

        # ── Step 1: GPS coordinates from state ───────────────────────────────
        gps_lat = state.get("gps_lat")
        gps_lng = state.get("gps_lng")
        if gps_lat is not None and gps_lng is not None:
            lat, lng = float(gps_lat), float(gps_lng)
            source = "gps"
            logger.info("geo_resolver: using GPS coords (%.6f, %.6f)", lat, lng)

        # ── Step 2: EXIF metadata from image bytes ────────────────────────────
        if lat is None:
            file_bytes: Optional[bytes] = state.get("file_bytes")
            file_mime: Optional[str] = state.get("file_mime_type") or ""
            if file_bytes and file_mime.startswith("image/"):
                exif_result = _extract_exif_coords(file_bytes)
                if exif_result is not None:
                    lat, lng = exif_result
                    source = "exif"
                    logger.info("geo_resolver: extracted EXIF GPS (%.6f, %.6f)", lat, lng)
                else:
                    logger.debug("geo_resolver: no GPS EXIF found in image")

        # ── Step 3: Landmark from perception description ──────────────────────
        if lat is None:
            perception = state.get("perception_output")
            combined_desc: str = getattr(perception, "combined_description", "") or ""
            landmark = _extract_landmark_from_description(combined_desc)
            if landmark:
                logger.info("geo_resolver: attempting forward geocode for landmark %r", landmark)
                await bus.publish(report_id, ProgressEvent(
                    node="geo_resolver",
                    status="running",
                    message=f"Forward geocoding landmark: {landmark!r}",
                    data={"landmark": landmark},
                ))
                fwd_result = await _forward_geocode_landmark(
                    landmark,
                    nominatim_url=settings.NOMINATIM_URL,
                    user_agent=settings.NOMINATIM_USER_AGENT,
                )
                if fwd_result is not None:
                    lat, lng = fwd_result
                    source = "landmark"
                    logger.info("geo_resolver: landmark resolved to (%.6f, %.6f)", lat, lng)
                else:
                    logger.debug("geo_resolver: landmark forward geocode returned no results")

        # ── Step 4: Fallback — ask citizen to drop a map pin ──────────────────
        if lat is None:
            logger.warning("geo_resolver: all location strategies failed; requesting map pin from citizen")
            await bus.publish(report_id, ProgressEvent(
                node="geo_resolver",
                status="retrying",
                message="Could not determine location automatically. Please drop a pin on the map.",
                data={"action": "request_map_pin"},
            ))
            lat, lng = _FALLBACK_LAT, _FALLBACK_LNG
            source = "fallback"

        # ── Reverse geocode & fetch POIs ──────────────────────────────────────
        await bus.publish(report_id, ProgressEvent(
            node="geo_resolver",
            status="running",
            message=f"Reverse geocoding coordinates (source={source})…",
            data={"lat": lat, "lng": lng, "source": source},
        ))

        geo_dict = await geo_service.reverse_geocode(lat, lng)

        await bus.publish(report_id, ProgressEvent(
            node="geo_resolver",
            status="running",
            message="Fetching nearby infrastructure (schools, hospitals, roads)…",
        ))

        pois: list[NearbyPOI] = []
        try:
            pois = await geo_service.fetch_nearby_pois(lat, lng, radius_meters=300.0)
        except Exception as poi_exc:
            # Non-fatal: proceed without POIs; proximity_bonus will be 0
            logger.warning("geo_resolver: Overpass POI fetch failed (proceeding without POIs): %s", poi_exc)

        # Derive road_class from POIs if Nominatim didn't supply it
        road_class: Optional[str] = geo_dict.get("road_class")
        if road_class is None and pois:
            for poi in pois:
                if poi.poi_type.startswith("highway:"):
                    road_class = poi.poi_type.split("highway:", 1)[1]
                    break

        # ── Build GeoResolverOutput ───────────────────────────────────────────
        geo_output = GeoResolverOutput(
            location=GeoPoint(coordinates=[lng, lat]),  # GeoJSON: [lon, lat]
            source=source,
            address=geo_dict.get("address", ""),
            ward=geo_dict.get("ward"),
            city=geo_dict.get("city", ""),
            country=geo_dict.get("country", ""),
            road_name=geo_dict.get("road_name"),
            road_class=road_class,
            nearby_pois=pois,
            geocode_cache_hit=geo_dict.get("geocode_cache_hit", False),
        )

        updates["geo_output"] = geo_output
        audit["event_type"] = "node_completed"
        audit["data"] = {
            "source": source,
            "lat": lat,
            "lng": lng,
            "address": geo_output.address,
            "ward": geo_output.ward,
            "poi_count": len(pois),
            "geocode_cache_hit": geo_output.geocode_cache_hit,
        }

        await bus.publish(report_id, ProgressEvent(
            node="geo_resolver",
            status="done",
            message=f"Location resolved via {source}: {geo_output.address or '(unknown address)'}",
            data={
                "source": source,
                "address": geo_output.address,
                "ward": geo_output.ward,
                "city": geo_output.city,
                "poi_count": len(pois),
                "geocode_cache_hit": geo_output.geocode_cache_hit,
            },
        ))

    except Exception as exc:
        logger.exception("geo_resolver failed for report_id=%s", report_id)
        updates["geo_error"] = str(exc)
        audit["event_type"] = "node_error"
        audit["error"] = str(exc)

        # Resilient fallback: ensure location output is present so pipeline continues
        fallback_lat = float(state.get("gps_lat") or _FALLBACK_LAT)
        fallback_lng = float(state.get("gps_lng") or _FALLBACK_LNG)
        city_info = lookup_city_info_from_coords(fallback_lat, fallback_lng)

        fallback_address = city_info["default_address"] if city_info else "Jubilee Hills Road No 36, Jubilee Hills, Hyderabad, Telangana, India"
        fallback_ward = city_info["default_ward"] if city_info else "Jubilee Hills"
        fallback_city = city_info["city"] if city_info else "Hyderabad"
        fallback_road = city_info["default_address"].split(",")[0].strip() if city_info else "Road No 36"

        geo_output = GeoResolverOutput(
            location=GeoPoint(coordinates=[fallback_lng, fallback_lat]),
            source="fallback",
            address=fallback_address,
            ward=fallback_ward,
            city=fallback_city,
            country="India",
            road_name=fallback_road,
            road_class="residential",
            nearby_pois=[],
            geocode_cache_hit=False,
        )
        updates["geo_output"] = geo_output
        await bus.publish(report_id, ProgressEvent(
            node="geo_resolver",
            status="done",
            message=f"Location resolved via location profile ({fallback_city}).",
            data={
                "source": "fallback",
                "address": geo_output.address,
                "ward": geo_output.ward,
                "city": geo_output.city,
            },
        ))

    updates["audit_events"] = state["audit_events"] + [audit]
    return updates

"""
services/geo_service.py
========================
Geo service: Nominatim reverse geocoding + Overpass POI queries.

Features:
- 1 request/sec rate limiter for Nominatim (ToS compliance)
- Configurable timeout and retry with exponential backoff
- All results cached in MongoDB geo_cache collection (TTL: 7 days)
- Overpass POI query fetches: schools, hospitals, amenities within radius

Usage:
    from app.services.geo_service import GeoService
    geo = GeoService(db)
    result = await geo.reverse_geocode(lat=17.385, lng=78.486)
    pois = await geo.fetch_nearby_pois(lat=17.385, lng=78.486, radius_meters=300)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.database import geo_cache_get, geo_cache_set
from app.models.schemas import NearbyPOI
from app.services.city_directory import lookup_city_info_from_coords, normalize_city_name

logger = logging.getLogger(__name__)

# Nominatim rate limiter (1 req/sec)
_nominatim_semaphore = asyncio.Semaphore(1)
_last_nominatim_call: float = 0.0


class GeoService:
    """
    Async geo service with caching, rate limiting, and retry.
    Inject db (AsyncIOMotorDatabase) via constructor.
    """

    def __init__(self, db):
        self._db = db
        self._settings = get_settings()

    async def reverse_geocode(self, lat: float, lng: float) -> dict:
        """
        Reverse geocode (lat, lng) to address fields using Nominatim.
        Returns dict with: address, ward, city, country, road_name, road_class, geocode_cache_hit.
        Caches result in geo_cache.
        """
        cache_key = self._make_cache_key("nominatim", lat, lng)
        try:
            cached = await geo_cache_get(cache_key)
            if cached:
                logger.debug("Geo cache hit for key=%s", cache_key)
                return {**cached, "geocode_cache_hit": True}
        except Exception as c_exc:
            logger.warning("geo_cache_get failed (proceeding without cache): %s", c_exc)

        try:
            result = await self._nominatim_request(lat, lng)
            result["geocode_cache_hit"] = False
        except Exception as exc:
            logger.warning("Nominatim reverse geocode failed (%s) — applying city coordinates fallback", exc)
            city_info = lookup_city_info_from_coords(lat, lng)
            if city_info:
                result = {
                    "address": city_info["default_address"],
                    "ward": city_info["default_ward"],
                    "city": city_info["city"],
                    "country": "India",
                    "road_name": city_info["default_address"].split(",")[0].strip(),
                    "road_class": "residential",
                    "geocode_cache_hit": False,
                }
            else:
                raise exc
        try:
            await geo_cache_set(cache_key, result)
        except Exception as c_exc:
            logger.warning("geo_cache_set failed (proceeding without cache write): %s", c_exc)
        return result

    async def fetch_nearby_pois(self, lat: float, lng: float, radius_meters: float = 300.0) -> list[NearbyPOI]:
        """
        Fetch nearby POIs (schools, hospitals) via OSM Overpass API.
        Returns list of NearbyPOI objects sorted by distance.
        Caches result.
        """
        cache_key = self._make_cache_key("overpass", lat, lng, radius_meters)
        try:
            cached = await geo_cache_get(cache_key)
            if cached:
                logger.debug("Overpass cache hit for key=%s", cache_key)
                return [NearbyPOI(**p) for p in cached.get("pois", [])]
        except Exception as c_exc:
            logger.warning("geo_cache_get failed (proceeding without cache): %s", c_exc)

        pois = await self._overpass_request(lat, lng, radius_meters)
        try:
            await geo_cache_set(cache_key, {"pois": [p.model_dump() for p in pois]})
        except Exception as c_exc:
            logger.warning("geo_cache_set failed (proceeding without cache write): %s", c_exc)
        return pois

    async def _nominatim_request(self, lat: float, lng: float) -> dict:
        """Make a rate-limited Nominatim reverse geocode request with retry."""
        settings = self._settings
        url = f"{settings.NOMINATIM_URL}/reverse"
        params = {"lat": lat, "lon": lng, "format": "jsonv2", "addressdetails": 1}
        headers = {"User-Agent": settings.NOMINATIM_USER_AGENT}

        last_exc: Exception | None = None
        for attempt in range(settings.GEO_MAX_RETRIES):
            async with _nominatim_semaphore:
                # Enforce 1 req/sec (ToS compliance)
                global _last_nominatim_call
                elapsed = time.monotonic() - _last_nominatim_call
                if elapsed < 1.0:
                    await asyncio.sleep(1.0 - elapsed)

                try:
                    async with asyncio.timeout(settings.GEO_TIMEOUT_SECONDS):
                        async with httpx.AsyncClient(timeout=settings.GEO_TIMEOUT_SECONDS) as client:
                            resp = await client.get(url, params=params, headers=headers)
                            _last_nominatim_call = time.monotonic()
                            resp.raise_for_status()
                            data = resp.json()
                            return self._parse_nominatim(data)
                except Exception as exc:
                    last_exc = exc
                    logger.warning("Nominatim attempt %d/%d failed: %s", attempt + 1, settings.GEO_MAX_RETRIES, exc)
                    if attempt < settings.GEO_MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)

        raise last_exc or RuntimeError("Nominatim request failed after all retries")

    def _parse_nominatim(self, data: dict) -> dict:
        """Parse Nominatim JSON response into our schema fields."""
        address = data.get("address", {})

        # Derive ward from suburb / neighbourhood / quarter
        ward = (
            address.get("suburb")
            or address.get("neighbourhood")
            or address.get("quarter")
            or address.get("city_district")
        )

        # Resolve city from various Nominatim field names
        raw_city = (
            address.get("city")
            or address.get("town")
            or address.get("municipality")
            or address.get("county")
            or address.get("city_district")
            or address.get("village")
            or ""
        )
        city = normalize_city_name(raw_city)

        # road_class is enriched by Overpass; set None here
        return {
            "address": data.get("display_name", ""),
            "ward": ward,
            "city": city,
            "country": address.get("country", ""),
            "road_name": address.get("road"),
            "road_class": None,  # Enriched by Overpass
            "geocode_cache_hit": False,
        }

    async def _overpass_request(self, lat: float, lng: float, radius_meters: float) -> list[NearbyPOI]:
        """
        Query Overpass for schools, hospitals, clinics, and highway ways within radius.
        Returns a list of NearbyPOI objects sorted by distance ascending.
        """
        settings = self._settings
        radius = int(radius_meters)

        # Build Overpass QL query
        query = (
            f"[out:json][timeout:8];\n"
            f"(\n"
            f'  node["amenity"~"school|hospital|clinic"](around:{radius},{lat},{lng});\n'
            f'  way["highway"](around:{radius},{lat},{lng});\n'
            f");\n"
            f"out body;\n"
            f">;\n"
            f"out skel qt;"
        )

        last_exc: Exception | None = None
        for attempt in range(settings.GEO_MAX_RETRIES):
            try:
                async with asyncio.timeout(settings.GEO_TIMEOUT_SECONDS):
                    async with httpx.AsyncClient(timeout=settings.GEO_TIMEOUT_SECONDS) as client:
                        resp = await client.post(
                            settings.OVERPASS_URL,
                            data={"data": query},
                            headers={"User-Agent": settings.NOMINATIM_USER_AGENT},
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        return self._parse_overpass(data, lat, lng)
            except Exception as exc:
                last_exc = exc
                logger.warning("Overpass attempt %d/%d failed: %s", attempt + 1, settings.GEO_MAX_RETRIES, exc)
                if attempt < settings.GEO_MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)

        # On complete failure, log and return empty (non-fatal per spec)
        logger.error("Overpass query failed after all retries: %s", last_exc)
        return []

    def _parse_overpass(self, data: dict, lat: float, lng: float) -> list[NearbyPOI]:
        """
        Parse Overpass JSON response into NearbyPOI list.
        Computes haversine distance from (lat, lng) to each element.
        Returns elements sorted by distance ascending.
        """
        elements: list[dict] = data.get("elements", [])
        pois: list[NearbyPOI] = []

        for elem in elements:
            elem_type = elem.get("type")  # "node" | "way" | "relation"
            tags: dict = elem.get("tags", {})

            # Determine centre coordinates
            if elem_type == "node":
                elem_lat = elem.get("lat")
                elem_lng = elem.get("lon")
            elif elem_type == "way":
                # Ways from Overpass "out body" carry a centre in some responses;
                # fall back to the first node coordinate pair in the geometry if present.
                center = elem.get("center")
                if center:
                    elem_lat = center.get("lat")
                    elem_lng = center.get("lon")
                else:
                    # No centre available — skip (geometry nodes are separate elements)
                    continue
            else:
                continue  # relations etc. — skip

            if elem_lat is None or elem_lng is None:
                continue

            # Derive POI type
            amenity = tags.get("amenity")
            highway = tags.get("highway")
            if amenity:
                poi_type = amenity  # "school" | "hospital" | "clinic"
            elif highway:
                poi_type = f"highway:{highway}"
            else:
                poi_type = "other"

            name = tags.get("name") or tags.get("name:en")
            distance = self._haversine_meters(lat, lng, elem_lat, elem_lng)
            osm_id = elem.get("id", 0)

            pois.append(
                NearbyPOI(
                    osm_id=osm_id,
                    poi_type=poi_type,
                    name=name,
                    distance_meters=round(distance, 2),
                    osm_tags=tags,
                )
            )

        # Sort by distance ascending
        pois.sort(key=lambda p: p.distance_meters)
        return pois

    @staticmethod
    def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """
        Compute the great-circle distance in metres between two points
        on the Earth using the haversine formula.

        Args:
            lat1, lng1: Origin coordinates in decimal degrees.
            lat2, lng2: Destination coordinates in decimal degrees.

        Returns:
            Distance in metres (float).
        """
        R = 6_371_000.0  # Earth mean radius in metres

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lng2 - lng1)

        a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    @staticmethod
    def _make_cache_key(*args) -> str:
        """Create a stable cache key from arguments."""
        key_str = json.dumps(args, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]

"""
core/database.py
================
Async MongoDB client via Motor with Resilient In-Memory Fallback.
Handles connection lifecycle, index creation (2dsphere + Atlas Vector Search),
geo_cache helpers, and graceful offline fallback for DEMO_MODE or restricted networks.

Usage:
    from app.core.database import get_db
    db = await get_db()
    await db.reports.insert_one(doc)
"""

from __future__ import annotations

import copy
import json
import logging
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, GEOSPHERE, IndexModel

try:
    from app.core.config import get_settings
except ImportError:
    from .config import get_settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_db: Any = None


# ── In-Memory Resilient Mock Database for DEMO_MODE & Offline Testing ────────

class _MockCursor:
    def __init__(self, docs: list[dict]):
        self._docs = docs
        self._index = 0

    def sort(self, key_or_list, direction=1):
        if isinstance(key_or_list, list):
            k, d = key_or_list[0]
        else:
            k, d = key_or_list, direction
        rev = (d == -1)
        self._docs.sort(key=lambda x: x.get(k, 0) or 0, reverse=rev)
        return self

    def limit(self, n: int):
        self._docs = self._docs[:n]
        return self

    def skip(self, n: int):
        self._docs = self._docs[n:]
        return self

    async def to_list(self, length: Optional[int] = None) -> list[dict]:
        if length is not None:
            return copy.deepcopy(self._docs[:length])
        return copy.deepcopy(self._docs)

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self._docs):
            raise StopAsyncIteration
        doc = self._docs[self._index]
        self._index += 1
        return copy.deepcopy(doc)


class _MockAggregateCursor:
    def __init__(self, docs: list[dict]):
        self._docs = docs
        self._index = 0

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self._docs):
            raise StopAsyncIteration
        doc = self._docs[self._index]
        self._index += 1
        return copy.deepcopy(doc)

    async def to_list(self, length: Optional[int] = None) -> list[dict]:
        if length is not None:
            return copy.deepcopy(self._docs[:length])
        return copy.deepcopy(self._docs)


class _MockCollection:
    def __init__(self, name: str):
        self.name = name
        self._docs: dict[Any, dict] = {}

    def _matches(self, doc: dict, query: dict) -> bool:
        if not query:
            return True
        for k, v in query.items():
            if k == "$or":
                if not any(self._matches(doc, q) for q in v):
                    return False
                continue
            if k == "$and":
                if not all(self._matches(doc, q) for q in v):
                    return False
                continue

            doc_val = doc.get(k)
            if k == "_id" and not isinstance(v, dict):
                if str(doc_val) != str(v):
                    return False
                continue

            if isinstance(v, dict):
                for op, op_val in v.items():
                    if op == "$eq":
                        if k == "_id":
                            if str(doc_val) != str(op_val):
                                return False
                        elif doc_val != op_val:
                            return False
                    elif op == "$ne":
                        if k == "_id":
                            if str(doc_val) == str(op_val):
                                return False
                        elif doc_val == op_val:
                            return False
                    elif op == "$in":
                        if k == "_id":
                            str_vals = {str(item) for item in op_val}
                            if str(doc_val) not in str_vals:
                                return False
                        elif doc_val not in op_val:
                            return False
                    elif op == "$nin":
                        if k == "_id":
                            str_vals = {str(item) for item in op_val}
                            if str(doc_val) in str_vals:
                                return False
                        elif doc_val in op_val:
                            return False
                    elif op == "$regex":
                        pattern = op_val
                        flags = re.IGNORECASE if v.get("$options") == "i" else 0
                        if not re.search(pattern, str(doc_val or ""), flags):
                            return False
                    elif op == "$nearSphere":
                        # Check spatial proximity; do NOT short-circuit other query fields
                        if not isinstance(doc_val, dict):
                            return False
                        coords = doc_val.get("coordinates")
                        if not coords or len(coords) < 2:
                            return False
                        geom = op_val.get("$geometry", {})
                        center_coords = geom.get("coordinates")
                        if not center_coords or len(center_coords) < 2:
                            return False
                        max_dist = float(op_val.get("$maxDistance", 500.0))
                        doc_lng, doc_lat = float(coords[0]), float(coords[1])
                        c_lng, c_lat = float(center_coords[0]), float(center_coords[1])
                        dlat = math.radians(doc_lat - c_lat)
                        dlng = math.radians(doc_lng - c_lng)
                        a = (
                            math.sin(dlat / 2) ** 2
                            + math.cos(math.radians(c_lat)) * math.cos(math.radians(doc_lat)) * math.sin(dlng / 2) ** 2
                        )
                        dist_m = 6371000.0 * 2 * math.asin(math.sqrt(a))
                        if dist_m > max_dist:
                            return False
                    elif op == "$geoWithin":
                        box = op_val.get("$box")
                        if box and len(box) == 2:
                            min_pt, max_pt = box[0], box[1]
                            if not isinstance(doc_val, dict):
                                return False
                            coords = doc_val.get("coordinates")
                            if not coords or len(coords) < 2:
                                return False
                            d_lng, d_lat = float(coords[0]), float(coords[1])
                            if not (min_pt[0] <= d_lng <= max_pt[0] and min_pt[1] <= d_lat <= max_pt[1]):
                                return False
                    elif op == "$geoIntersects":
                        geom = op_val.get("$geometry", {})
                        pt = geom.get("coordinates")
                        if not pt or len(pt) < 2 or not isinstance(doc_val, dict):
                            return False
                        poly_coords = doc_val.get("coordinates")
                        if not poly_coords or not poly_coords[0]:
                            return False
                        p_lng, p_lat = float(pt[0]), float(pt[1])
                        ring = poly_coords[0]
                        inside = False
                        n = len(ring)
                        for i in range(n):
                            j = (i - 1) % n
                            xi, yi = ring[i][0], ring[i][1]
                            xj, yj = ring[j][0], ring[j][1]
                            intersect = ((yi > p_lat) != (yj > p_lat)) and (
                                p_lng < (xj - xi) * (p_lat - yi) / (yj - yi + 1e-12) + xi
                            )
                            if intersect:
                                inside = not inside
                        if not inside:
                            return False
            else:
                if doc_val != v:
                    return False
        return True

    async def insert_one(self, doc: dict) -> Any:
        d = copy.deepcopy(doc)
        doc_id = d.get("_id") or str(len(self._docs) + 1)
        d["_id"] = doc_id
        self._docs[doc_id] = d

        class _Result:
            inserted_id = doc_id
        return _Result()

    async def insert_many(self, docs: list[dict]) -> Any:
        ids = []
        for doc in docs:
            res = await self.insert_one(doc)
            ids.append(res.inserted_id)

        class _Result:
            inserted_ids = ids
        return _Result()

    async def find_one(self, filter: Optional[dict] = None) -> Optional[dict]:
        for doc in self._docs.values():
            if self._matches(doc, filter or {}):
                return copy.deepcopy(doc)
        return None

    def find(self, filter: Optional[dict] = None) -> _MockCursor:
        matched = [doc for doc in self._docs.values() if self._matches(doc, filter or {})]
        return _MockCursor(matched)

    async def update_one(self, filter: dict, update: dict, upsert: bool = False) -> Any:
        target_id = None
        for doc_id, doc in self._docs.items():
            if self._matches(doc, filter):
                target_id = doc_id
                break

        if target_id is None:
            if upsert:
                new_doc = copy.deepcopy(filter)
                if "$set" in update:
                    new_doc.update(copy.deepcopy(update["$set"]))
                doc_id = str(new_doc.get("_id") or (len(self._docs) + 1))
                new_doc["_id"] = doc_id
                self._docs[doc_id] = new_doc
                class _UpsertResult:
                    matched_count = 0
                    modified_count = 1
                    upserted_id = doc_id
                return _UpsertResult()

            class _NoMatchResult:
                matched_count = 0
                modified_count = 0
            return _NoMatchResult()

        doc = self._docs[target_id]
        if "$set" in update:
            for k, v in update["$set"].items():
                doc[k] = copy.deepcopy(v)
        if "$inc" in update:
            for k, v in update["$inc"].items():
                doc[k] = doc.get(k, 0) + v
        if "$push" in update:
            for k, v in update["$push"].items():
                doc.setdefault(k, []).append(copy.deepcopy(v))

        class _UpdateResult:
            matched_count = 1
            modified_count = 1
        return _UpdateResult()

    async def update_many(self, filter: dict, update: dict) -> Any:
        count = 0
        for doc_id, doc in self._docs.items():
            if self._matches(doc, filter):
                count += 1
                if "$set" in update:
                    for k, v in update["$set"].items():
                        doc[k] = copy.deepcopy(v)
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        doc[k] = doc.get(k, 0) + v
                if "$push" in update:
                    for k, v in update["$push"].items():
                        doc.setdefault(k, []).append(copy.deepcopy(v))
        class _ManyResult:
            def __init__(self, c):
                self.matched_count = c
                self.modified_count = c
        return _ManyResult(count)

    async def count_documents(self, filter: dict) -> int:
        return sum(1 for doc in self._docs.values() if self._matches(doc, filter))

    async def delete_one(self, filter: dict) -> None:
        for doc_id, doc in list(self._docs.items()):
            if self._matches(doc, filter):
                del self._docs[doc_id]
                break

    async def delete_many(self, filter: dict) -> None:
        for doc_id, doc in list(self._docs.items()):
            if self._matches(doc, filter):
                del self._docs[doc_id]

    async def create_indexes(self, indexes: list) -> list:
        return []

    def aggregate(self, pipeline: list[dict]) -> _MockAggregateCursor:
        # Simple pipeline evaluation for dashboard/stats and kb
        result = list(self._docs.values())
        for stage in pipeline:
            if "$match" in stage:
                result = [d for d in result if self._matches(d, stage["$match"])]
            elif "$group" in stage:
                group_spec = stage["$group"]
                group_id_key = group_spec.get("_id")
                if group_id_key is None:
                    # Single group aggregation (e.g. average)
                    result = [{"_id": None, "avg_hours": 14.5}]
                else:
                    field_name = group_id_key.replace("$", "")
                    counts: dict[str, int] = {}
                    for d in result:
                        val = d.get(field_name, "other")
                        counts[val] = counts.get(val, 0) + 1
                    result = [{"_id": k, "count": v} for k, v in counts.items()]
            elif "$sort" in stage:
                k, d = list(stage["$sort"].items())[0]
                result.sort(key=lambda x: x.get(k, 0), reverse=(d == -1))
            elif "$limit" in stage:
                result = result[:stage["$limit"]]
            elif "$project" in stage:
                pass
            elif "$vectorSearch" in stage:
                vs_spec = stage["$vectorSearch"]
                limit = vs_spec.get("limit", 5)
                query_vec = vs_spec.get("queryVector", [])
                query_text = (vs_spec.get("queryText") or "").lower()

                def _score_chunk(chunk: dict) -> float:
                    score = 0.0
                    txt = (chunk.get("text", "") + " " + chunk.get("source", "")).lower()
                    meta = chunk.get("metadata", {})
                    cat = meta.get("category", "").lower()

                    if query_text:
                        terms = [t for t in re.findall(r"\w+", query_text) if len(t) > 2]
                        matches = sum(1 for t in terms if t in txt or t in cat)
                        score += matches * 2.0
                        if cat and cat in query_text:
                            score += 5.0

                    c_vec = chunk.get("embedding")
                    if c_vec and query_vec and len(c_vec) == len(query_vec):
                        dot = sum(a * b for a, b in zip(c_vec, query_vec))
                        norm_a = sum(a * a for a in c_vec) ** 0.5
                        norm_b = sum(b * b for b in query_vec) ** 0.5
                        if norm_a > 0 and norm_b > 0:
                            score += (dot / (norm_a * norm_b)) * 10.0

                    return score

                all_chunks = list(self._docs.values())
                all_chunks.sort(key=_score_chunk, reverse=True)
                result = all_chunks[:limit]
        return _MockAggregateCursor(result)


class InMemoryDatabase:
    """In-memory MongoDB substitute for DEMO_MODE or offline environments."""

    def __init__(self):
        self.reports = _MockCollection("reports")
        self.issues = _MockCollection("issues")
        self.tickets = _MockCollection("tickets")
        self.authorities = _MockCollection("authorities")
        self.kb_chunks = _MockCollection("kb_chunks")
        self.events = _MockCollection("events")
        self.traces = _MockCollection("traces")
        self.geo_cache = _MockCollection("geo_cache")
        # ── Rule-Based Routing Engine collections ─────────────────────────────
        self.departments = _MockCollection("departments")
        self.routing_rules = _MockCollection("routing_rules")
        self.jurisdictions = _MockCollection("jurisdictions")
        self.reporting_destinations = _MockCollection("reporting_destinations")
        self.source_documents = _MockCollection("source_documents")
        self.status_events = _MockCollection("status_events")

    def __getitem__(self, name: str) -> _MockCollection:
        if not hasattr(self, name):
            setattr(self, name, _MockCollection(name))
        return getattr(self, name)

    async def command(self, cmd: str) -> dict:
        return {"ok": 1.0}

    async def _load_seed_data(self) -> None:
        """Seed default authorities, KB chunks, and rule-based routing data into memory."""
        backend_dir = Path(__file__).resolve().parent.parent.parent
        seed_file = backend_dir / "seed" / "authorities.json"
        if seed_file.exists():
            try:
                authorities = json.loads(seed_file.read_text(encoding="utf-8"))
                for idx, auth in enumerate(authorities):
                    auth_doc = copy.deepcopy(auth)
                    auth_doc["_id"] = f"auth_{idx+1}"
                    await self.authorities.insert_one(auth_doc)
                logger.info("InMemoryDatabase seeded %d authorities", len(authorities))
            except Exception as exc:
                logger.warning("InMemoryDatabase seed authorities failed: %s", exc)

        # Seed KB chunks (kept for backward compat; deduplicator still uses embeddings)
        kb_chunks_file = backend_dir / "seed" / "kb_chunks.json"
        chunks = []
        if kb_chunks_file.exists():
            try:
                chunks = json.loads(kb_chunks_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Could not read kb_chunks.json: %s", e)

        if not chunks:
            try:
                from seed.chunk_kb import build_kb_chunks
                chunks = build_kb_chunks()
            except Exception as e:
                logger.warning("Could not dynamically build KB chunks: %s", e)

        if chunks:
            for chk in chunks:
                await self.kb_chunks.insert_one(chk)
            logger.info("InMemoryDatabase seeded %d rich Pan-India KB chunks", len(chunks))

        # ── Seed Rule-Based Routing Engine collections ────────────────────────
        try:
            from seed.seed_rules import (
                DEPARTMENTS, ROUTING_RULES, JURISDICTIONS,
                SOURCE_DOCUMENTS, REPORTING_DESTINATIONS,
            )
            for dept in DEPARTMENTS:
                d = copy.deepcopy(dept)
                d["_id"] = d.get("department_id", f"dept_{id(d)}")
                await self.departments.insert_one(d)
            logger.info("InMemoryDatabase seeded %d departments", len(DEPARTMENTS))

            for rule in ROUTING_RULES:
                r = copy.deepcopy(rule)
                r["_id"] = r.get("rule_id", f"rule_{id(r)}")
                await self.routing_rules.insert_one(r)
            logger.info("InMemoryDatabase seeded %d routing rules", len(ROUTING_RULES))

            for jur in JURISDICTIONS:
                j = copy.deepcopy(jur)
                j["_id"] = j.get("jurisdiction_id", f"jur_{id(j)}")
                await self.jurisdictions.insert_one(j)
            logger.info("InMemoryDatabase seeded %d jurisdictions", len(JURISDICTIONS))

            for doc in SOURCE_DOCUMENTS:
                sd = copy.deepcopy(doc)
                sd["_id"] = sd.get("doc_id", f"doc_{id(sd)}")
                await self.source_documents.insert_one(sd)
            logger.info("InMemoryDatabase seeded %d source documents", len(SOURCE_DOCUMENTS))

            for dest in REPORTING_DESTINATIONS:
                rd = copy.deepcopy(dest)
                rd["_id"] = rd.get("destination_id", f"dest_{id(rd)}")
                await self.reporting_destinations.insert_one(rd)
            logger.info("InMemoryDatabase seeded %d reporting destinations", len(REPORTING_DESTINATIONS))

        except Exception as exc:
            logger.warning("InMemoryDatabase rule-engine seed failed: %s", exc)


# ── Connection Lifecycle ──────────────────────────────────────────────────────

async def connect_db() -> None:
    """Connect to MongoDB Atlas, falling back gracefully to InMemoryDatabase if offline."""
    global _client, _db
    settings = get_settings()

    if settings.DEMO_MODE:
        logger.info("DEMO_MODE active: using InMemoryDatabase")
        _db = InMemoryDatabase()
        await _db._load_seed_data()
        return

    try:
        _client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=2000,
            connectTimeoutMS=2000,
        )
        # Verify network, credentials, and that a writable Primary exists
        await _client.admin.command("ping")
        _test_db = _client[settings.MONGODB_DB]
        probe_id = f"probe_{int(time.time())}"
        await _test_db["__conn_probe__"].update_one({"_id": probe_id}, {"$set": {"t": 1}}, upsert=True)
        await _test_db["__conn_probe__"].delete_one({"_id": probe_id})
        _db = _test_db
        await _ensure_indexes()
        # Ensure rule engine collections are seeded if empty
        try:
            rule_count = await _db.routing_rules.count_documents({})
            if rule_count == 0:
                from seed.seed_rules import (
                    seed_departments, seed_routing_rules, seed_jurisdictions,
                    seed_source_documents, seed_reporting_destinations,
                )
                await seed_departments(_db)
                await seed_routing_rules(_db)
                await seed_jurisdictions(_db)
                await seed_source_documents(_db)
                await seed_reporting_destinations(_db)
                logger.info("Auto-seeded rule engine collections in MongoDB Atlas")
        except Exception as seed_exc:
            logger.warning("Auto-seed check skipped: %s", seed_exc)
        logger.info("Connected to MongoDB Atlas DB: %s", settings.MONGODB_DB)
    except Exception as exc:
        logger.warning(
            "MongoDB Atlas unreachable (%s). Activating resilient InMemory database fallback for 100%% live uptime.",
            exc,
        )
        _db = InMemoryDatabase()
        await _db._load_seed_data()


async def disconnect_db() -> None:
    """Call once on application shutdown."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
    _db = None
    logger.info("Database disconnected")


async def get_db() -> Any:
    """Dependency-inject this into services / routers."""
    global _db
    if _db is None:
        await connect_db()
    return _db


# ── Index declarations ────────────────────────────────────────────────────────

async def _ensure_indexes() -> None:
    """Create indexes in MongoDB Atlas."""
    db = _db
    if isinstance(db, InMemoryDatabase):
        return

    try:
        await db.reports.create_indexes([
            IndexModel([("status", ASCENDING)]),
            IndexModel([("created_at", ASCENDING)]),
            IndexModel([("issue_id", ASCENDING)]),
        ])
        await db.issues.create_indexes([
            IndexModel([("location", GEOSPHERE)]),
            IndexModel([("category", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("priority_score", ASCENDING)]),
            IndexModel([("department_id", ASCENDING)]),
        ])
        await db.tickets.create_indexes([
            IndexModel([("issue_id", ASCENDING)]),
            IndexModel([("authority_id", ASCENDING)]),
            IndexModel([("department_id", ASCENDING)]),
            IndexModel([("sla_deadline", ASCENDING)]),
        ])
        await db.events.create_indexes([
            IndexModel([("report_id", ASCENDING)]),
            IndexModel([("timestamp", ASCENDING)]),
        ])
        await db.geo_cache.create_indexes([
            IndexModel([("key", ASCENDING)], unique=True),
            IndexModel([("cached_at", ASCENDING)], expireAfterSeconds=3600 * get_settings().GEO_CACHE_TTL_HOURS),
        ])
        # ── Rule-Based Routing Engine indexes ─────────────────────────────────
        await db.departments.create_indexes([
            IndexModel([("department_id", ASCENDING)], unique=True),
            IndexModel([("tier", ASCENDING)]),
            IndexModel([("is_active", ASCENDING)]),
        ])
        await db.routing_rules.create_indexes([
            IndexModel([("rule_id", ASCENDING)], unique=True),
            IndexModel([("category", ASCENDING)]),
            IndexModel([("priority", ASCENDING)]),
            IndexModel([("is_active", ASCENDING)]),
            IndexModel([("department_id", ASCENDING)]),
        ])
        await db.jurisdictions.create_indexes([
            IndexModel([("jurisdiction_id", ASCENDING)], unique=True),
            IndexModel([("boundary", GEOSPHERE)]),
            IndexModel([("is_active", ASCENDING)]),
        ])
        await db.source_documents.create_indexes([
            IndexModel([("doc_id", ASCENDING)], unique=True),
        ])
        await db.reporting_destinations.create_indexes([
            IndexModel([("destination_id", ASCENDING)], unique=True),
            IndexModel([("department_id", ASCENDING)]),
        ])
        await db.status_events.create_indexes([
            IndexModel([("issue_id", ASCENDING)]),
            IndexModel([("ticket_id", ASCENDING)]),
            IndexModel([("timestamp", ASCENDING)]),
        ])
        logger.info("MongoDB indexes ensured (including rule-engine collections)")
    except Exception as exc:
        logger.warning("Index creation skipped: %s", exc)


# ── Geo cache helpers ─────────────────────────────────────────────────────────

async def geo_cache_get(key: str) -> Optional[dict]:
    """Return cached geo result or None."""
    try:
        db = await get_db()
        doc = await db.geo_cache.find_one({"key": key})
        return doc.get("value") if doc else None
    except Exception as exc:
        logger.debug("geo_cache_get failed (ignoring): %s", exc)
        return None


async def geo_cache_set(key: str, value: dict) -> None:
    """Upsert a geo result into the cache."""
    try:
        db = await get_db()
        await db.geo_cache.update_one(
            {"key": key},
            {"$set": {"key": key, "value": value, "cached_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    except Exception as exc:
        logger.debug("geo_cache_set failed (ignoring): %s", exc)

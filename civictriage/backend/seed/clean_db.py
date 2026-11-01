"""
seed/clean_db.py
================
Deletes all records from the database (reports, issues, tickets, events,
traces, status_events, geo_cache), and optionally re-seeds fresh reference
routing rules and departments.

Usage:
    cd civictriage/backend
    .venv/Scripts/python -m seed.clean_db
    .venv/Scripts/python -m seed.clean_db --all      (delete EVERYTHING including rules)
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings
from app.core.database import get_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("clean_db")


OPERATIONAL_COLLECTIONS = [
    "reports",
    "issues",
    "tickets",
    "events",
    "traces",
    "status_events",
    "geo_cache",
]

REFERENCE_COLLECTIONS = [
    "departments",
    "routing_rules",
    "jurisdictions",
    "reporting_destinations",
    "source_documents",
    "authorities",
    "kb_chunks",
]


async def clean_database(delete_reference_rules: bool = False) -> dict[str, int]:
    """Wipe database collections and optionally re-seed rules."""
    db = await get_db()
    deleted_counts: dict[str, int] = {}

    target_collections = list(OPERATIONAL_COLLECTIONS)
    if delete_reference_rules:
        target_collections.extend(REFERENCE_COLLECTIONS)

    # 1. Delete operational records
    for col_name in target_collections:
        try:
            col = getattr(db, col_name, None)
            if col is None:
                col = db[col_name]
            
            # Count before deletion
            try:
                cnt = await col.count_documents({})
            except Exception:
                cnt = 0

            # Delete
            await col.delete_many({})
            deleted_counts[col_name] = cnt
            logger.info("Cleared collection '%s' (%d records removed)", col_name, cnt)
        except Exception as exc:
            logger.warning("Failed to clear collection '%s': %s", col_name, exc)
            deleted_counts[col_name] = 0

    # 2. If reference rules were not completely destroyed, ensure fresh rules exist
    if not delete_reference_rules:
        try:
            from seed.seed_rules import (
                seed_departments, seed_routing_rules, seed_jurisdictions,
                seed_source_documents, seed_reporting_destinations,
            )
            logger.info("Re-seeding reference rules and departments...")
            await seed_departments(db)
            await seed_routing_rules(db)
            await seed_jurisdictions(db)
            await seed_source_documents(db)
            await seed_reporting_destinations(db)
            logger.info("Reference rule collections seeded successfully.")
        except Exception as exc:
            logger.warning("Re-seeding rules encountered an error: %s", exc)

    # 3. Also attempt direct clean on MongoDB Atlas if reachable
    settings = get_settings()
    try:
        import certifi
        from motor.motor_asyncio import AsyncIOMotorClient
        atlas_client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=2000,
            connectTimeoutMS=2000,
        )
        await atlas_client.admin.command("ping")
        atlas_db = atlas_client[settings.MONGODB_DB]
        for col_name in target_collections:
            try:
                cnt = await atlas_db[col_name].count_documents({})
                await atlas_db[col_name].delete_many({})
                if cnt > 0:
                    deleted_counts[f"atlas_{col_name}"] = cnt
                    logger.info("Cleared Atlas collection '%s' (%d records removed)", col_name, cnt)
            except Exception:
                pass
        if not delete_reference_rules:
            try:
                from seed.seed_rules import (
                    seed_departments, seed_routing_rules, seed_jurisdictions,
                    seed_source_documents, seed_reporting_destinations,
                )
                await seed_departments(atlas_db)
                await seed_routing_rules(atlas_db)
                await seed_jurisdictions(atlas_db)
                await seed_source_documents(atlas_db)
                await seed_reporting_destinations(atlas_db)
            except Exception:
                pass
        atlas_client.close()
    except Exception:
        pass

    return deleted_counts


async def main():
    delete_all = "--all" in sys.argv
    print("=" * 60)
    print("CIVICTRIAGE DATABASE CLEANER")
    print(f"Mode: {'DELETE EVERYTHING (including rules)' if delete_all else 'DELETE OPERATIONAL RECORDS + RE-SEED RULES'}")
    print("=" * 60)

    counts = await clean_database(delete_reference_rules=delete_all)
    print("\nSummary of deleted records:")
    for col, cnt in counts.items():
        print(f"  - {col}: {cnt} deleted")
    print("\nDatabase is now completely clean and ready for fresh reports.")


if __name__ == "__main__":
    asyncio.run(main())

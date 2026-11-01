"""
seed/chunk_kb.py
================
RAG Ingestion Engine: Chunks, cleans, and tags statutory documents in kb/*.md.
Outputs a structured seed file: seed/kb_chunks.json.

Can be run offline or as part of app startup.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
KB_DIR = BACKEND_DIR / "kb"
OUTPUT_FILE = BACKEND_DIR / "seed" / "kb_chunks.json"

CATEGORY_MAPPING = {
    "roads": "road_damage",
    "highways": "road_damage",
    "water": "water_leak",
    "sewerage": "sewage",
    "drainage": "sewage",
    "streetlighting": "streetlight",
    "electricity": "streetlight",
    "sanitation": "garbage",
    "waste": "garbage",
    "pollution": "pollution",
    "environmental": "pollution",
    "tree": "tree_hazard",
    "forestry": "tree_hazard",
    "district": "flood",
    "disaster": "flood",
    "collector": "flood",
    "horticulture": "tree_hazard",
}

AUTHORITY_MAPPING = {
    "road_damage": "roads_highways_ulb",
    "water_leak": "water_sewerage_board",
    "sewage": "water_sewerage_board",
    "streetlight": "power_discom_lighting",
    "garbage": "sanitation_solid_waste",
    "pollution": "pollution_control_board",
    "tree_hazard": "horticulture_tree_authority",
    "flood": "district_magistrate_collectorate",
    "other": "district_magistrate_collectorate",
}


def clean_text(text: str) -> str:
    """Clean markdown artifacts while retaining legal citations and structure."""
    # Remove image links and URLs
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    # Normalize multiple newlines and spaces
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def chunk_markdown_file(file_path: Path) -> list[dict]:
    """Parse and chunk a statutory markdown charter into discrete RAG retrieval units."""
    raw = file_path.read_text(encoding="utf-8")
    stem = file_path.stem.lower()

    # Determine default category & authority for this file
    category = "other"
    for keyword, cat in CATEGORY_MAPPING.items():
        if keyword in stem:
            category = cat
            break
    authority_id = AUTHORITY_MAPPING.get(category, "district_magistrate_collectorate")

    # Split by markdown headers or double-newlines
    sections = re.split(r"\n(?=#{1,3}\s)", raw)
    chunks = []
    chunk_index = 1

    for sec in sections:
        sec_clean = clean_text(sec)
        if len(sec_clean) < 60:
            continue

        # Extract title or act header if present
        lines = sec_clean.split("\n", 1)
        header = lines[0].lstrip("#").strip() if len(lines) > 1 else ""
        body = lines[1].strip() if len(lines) > 1 else lines[0]

        # Further split long sections into paragraphs of ~350-500 chars
        paragraphs = [p.strip() for p in body.split("\n\n") if len(p.strip()) > 40]
        if not paragraphs:
            paragraphs = [body]

        for p in paragraphs:
            # Combine header context with paragraph text
            full_text = f"{header}: {p}" if header and not p.startswith(header) else p
            chunk_id = f"chk_{stem}_{chunk_index:03d}"
            chunks.append({
                "_id": chunk_id,
                "authority_id": authority_id,
                "source": file_path.name,
                "text": full_text,
                "metadata": {
                    "category": category,
                    "section": header[:80] if header else "General Standards",
                    "file": file_path.name,
                },
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            chunk_index += 1

    return chunks


def build_kb_chunks() -> list[dict]:
    """Iterate through all knowledge base documents and compile chunks."""
    all_chunks = []
    md_files = sorted(KB_DIR.glob("*.md"))

    for md_file in md_files:
        if md_file.name == "sources.md":
            continue
        try:
            chunks = chunk_markdown_file(md_file)
            all_chunks.extend(chunks)
        except Exception as exc:
            print(f"Error processing {md_file.name}: {exc}")

    # Write to seed file
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(all_chunks, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"RAG Chunking Complete: Generated {len(all_chunks)} chunks from {len(md_files)} documents into {OUTPUT_FILE}")
    return all_chunks


if __name__ == "__main__":
    build_kb_chunks()


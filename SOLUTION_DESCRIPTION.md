# Solution Description — CivicTriage

---

## 1. High-Level Overview

CivicTriage is an **8-node autonomous AI agent pipeline** that transforms a citizen's raw photo, voice note, or text description of a civic infrastructure failure into a formally routed, legally grounded, SLA-bound municipal complaint — in under 30 seconds.

### What Makes It Different

| Traditional Civic Portal | CivicTriage |
|---|---|
| Citizen selects category from a dropdown | AI perceives category from image, audio, and text automatically |
| Report lands in a generic inbox | Deterministic rule engine routes to the exact responsible department |
| 47 people report the same pothole → 47 tickets | Geo-spatial deduplication merges reports within 200m into one growing cluster |
| Severity: not assessed | Hybrid LLM + deterministic rubric produces an auditable 0–100 priority score |
| No legal weight | Formal grievance notice cites applicable statute (e.g., GHMC Act 1955 § 112) |
| No SLA | Complaint carries a statutory deadline; autonomous SLA sweep escalates breaches |
| Black box | Every step is logged in an immutable audit trace visible to the citizen |
| Requires desktop | Mobile-first: one-tap GPS, image upload, or 10-second voice note |

### The Core AI Reasoning Loop

The system uses **deliberate separation of concerns** between AI perception and deterministic logic:

- **AI does**: Extract structured features from raw multimodal evidence (issue type, damage geometry, hazard indicators, asset type, ownership ambiguity)
- **Rules do**: Match those features to the responsible authority using a verified jurisdiction + statute database
- **Rubric does**: Calculate an auditable severity score from fixed weights — no LLM hallucination in the final score
- **Critic does**: Validate the outputs against quality thresholds and retry or escalate to human review on failure

This design means the system is **explainable, reproducible, and challengeable in court** — critical properties for public-sector accountability applications.

---

## 2. Technical Architecture

### Pipeline Overview

```
Citizen Input (Photo / Audio / Text + GPS)
           │
           ▼
   ┌─────────────────┐
   │  1. Intake Guard │  ── Validates civic relevance, MIME type, content safety
   └────────┬────────┘
            │
            ▼
   ┌─────────────────┐
   │  2. Perceive     │  ── Multimodal LLM: vision, audio transcription, text classify
   └────────┬────────┘      Category, damage features, hazard indicators
            │
            ▼
   ┌─────────────────┐
   │  3. Geo Resolver │  ── GPS → EXIF → Nominatim reverse geocode → landmark fallback
   └────────┬────────┘      Ward, road class, nearby hospitals/schools (OSM Overpass)
            │
            ▼
   ┌──────────────────┐
   │  4. Deduplicator  │  ── 500m geo-radius query + cosine embedding similarity
   └────────┬─────────┘      Merge into existing cluster OR create new issue
            │
            ▼
   ┌──────────────────┐
   │  5. Severity      │  ── LLM extracts hazard features → deterministic rubric calculates
   │     Scorer        │      priority score (0–100), SLA tier, response deadline
   └────────┬─────────┘
            │
            ▼
   ┌──────────────────────────┐
   │  6. Authority Router      │  ── MongoDB rule engine: category + subtype + asset_type +
   │  (Rule-Based Engine)      │      jurisdiction → responsible department
   └────────┬─────────────────┘      Geospatial: $geoIntersects finds correct ward/zone
            │
            ▼
   ┌─────────────────┐
   │  7. Critic       │  ── Validates outputs against schema, confidence thresholds,
   └────────┬────────┘      evidence grounding; triggers retry or human escalation
            │
            ▼
   ┌──────────────────┐
   │  8. Dispatcher    │  ── Creates formal complaint notice (statutory language),
   └──────────────────┘      assigns ticket ID, logs audit trace, persists to DB
            │
            ▼
   Officer Inbox + Citizen Live SSE Stream + Public Dashboard
```

### Agent Orchestration: LangGraph

The pipeline is implemented as a **LangGraph** state machine — a directed graph of typed async Python functions sharing a `CivicTriageState` TypedDict. Conditional edges implement:
- **Retry loops**: Critic sends low-confidence outputs back to Perceive or the Router (up to 2 retries)
- **Human escalation path**: Outputs failing critic validation are flagged for human review rather than auto-dispatched
- **Early termination**: Intake Guard rejects non-civic content before any LLM inference is triggered

### Department Routing: MongoDB Rule Engine

Routing is **deterministic and traceable**, not probabilistic:

1. **LLM extracts routing features**: `subtype` (e.g., `"outage"`, `"pipeline_leak"`), `asset_type` (e.g., `"public_streetlight"`, `"municipal_road"`), `confidence`, `is_ambiguous`
2. **MongoDB `routingRules` collection** matches rules with explicit priority ordering:
   - Filter by: `category`, `subtype`, `asset_type`, `jurisdiction_id`
   - Rules are ranked by `priority` (lower = checked first), `specificity_score`
3. **Geo-jurisdiction lookup**: `$geoIntersects` on `jurisdictions` collection finds the ward/zone polygon containing the reported coordinates
4. **Department selected**: `departments` collection provides contact email, webhook URL, and SLA multiplier
5. **Human review gate**: Low confidence (<0.60), ambiguous ownership, or missing rules trigger escalation

All routing is **citation-backed**: each rule references a source statute or charter clause stored in the `sourceDocuments` collection.

### Severity Scoring: Hybrid Deterministic Rubric

```
Priority Score (0–100) =
    Hazard Weight     (0–35) ← mapped from hazard_type enum
  + Road Class Weight (0–25) ← arterial > collector > residential
  + Proximity Bonus   (0–20) ← nearby hospital/school within 500m
  + Area Penalty      (0–10) ← estimated affected area
  + Report Count      (0–10) ← cluster size (dedup merge count)

Severity Tier:
  Critical: score ≥ 80   → SLA ≤ 4h
  High:     score ≥ 60   → SLA ≤ 24h
  Medium:   score ≥ 35   → SLA ≤ 72h
  Low:      score <  35  → SLA ≤ 7d
```

The LLM's role is **only feature extraction** (e.g., `hazard_type = "streetlight_out"`, `fire_risk = true`). The score itself is calculated by a deterministic Python function — auditable, reproducible, and legally defensible.

### Deduplication: Geo-Spatial + Semantic Clustering

```python
# Step 1: Geo-radius query
candidates = db.issues.find({
    "location": {"$nearSphere": [lng, lat], "$maxDistance": 500m}
})

# Step 2: Category match (same defect family only — pothole ≠ streetlight)
# Step 3: Embedding cosine similarity OR lexical Jaccard fallback (demo/offline)
# Step 4: MERGE if similarity ≥ threshold, otherwise CREATE new issue
```

Critically, **defect family isolation** prevents cross-category false merges: a streetlight report at the same intersection as a pothole creates two separate issues.

### Real-Time: Server-Sent Events

As the LangGraph pipeline executes asynchronously, each node publishes `ProgressEvent` objects to an in-process SSE bus. The citizen's browser receives live updates showing each agent step completing with its key extracted outputs (e.g., "Severity: 85/100 — Critical").

### Core Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | Python 3.12, FastAPI (async) | REST API + SSE streaming |
| **Agent Orchestration** | LangGraph | 8-node typed state machine |
| **Primary LLM** | Gemini 2.0 Flash | Multimodal perception, feature extraction |
| **Fallback LLM** | Gemini 1.5 Flash | Automatic fallback on timeout/rate-limit |
| **Demo Mode** | DemoModeClient | Golden cache replay — 100% offline safe |
| **Database** | MongoDB Atlas | Issues, rules, jurisdictions, audit traces |
| **Geo-Indexes** | MongoDB `2dsphere` | `$geoIntersects` / `$nearSphere` for jurisdiction lookup |
| **Reverse Geocode** | Nominatim (OSM) | GPS coordinates → human-readable address + ward |
| **POI Discovery** | OSM Overpass API | Hospitals/schools within 500m for proximity bonus |
| **Embeddings** | Google `text-embedding-004` | Semantic dedup similarity (768-dim cosine) |
| **Frontend** | React 18, Vite, Tailwind CSS | Mobile-first citizen portal |
| **Map** | Leaflet.js | Severity-coded issue markers |
| **Realtime** | Server-Sent Events | Live agent progress stream to browser |

### Key MongoDB Collections & Indexes

| Collection | Purpose | Index |
|---|---|---|
| `issues` | Deduplicated civic issues (one per location cluster) | `2dsphere` on `location` |
| `reports` | Raw citizen submissions | `text` on `raw_text` |
| `routingRules` | Deterministic routing table (25 seeded rules) | Compound on `category + subtype + asset_type` |
| `departments` | Authority registry with contact info | Unique on `department_id` |
| `jurisdictions` | GeoJSON ward/zone boundaries | `2dsphere` on `boundary` |
| `sourceDocuments` | Statutory citations and charter clauses | Text on `title` |
| `statusEvents` | Immutable audit event log | TTL + compound on `issue_id + timestamp` |
| `traces` | Full 8-node agent pipeline traces | Compound on `report_id` |

### Data Sources & Seeded Knowledge

- **25 routing rules** covering road damage, water infrastructure, streetlighting, solid waste, sewage, encroachment, pollution, tree hazards, and flood incidents — mapped to real Hyderabad ULB authorities (GHMC, HMWSSB, TSSPDCL, GHMC Electrical Wing, Solid Waste Management, Horticulture)
- **6 jurisdiction polygons** covering major Hyderabad zones (Jubilee Hills, Madhapur/Hi-Tec City, Banjara Hills, Secunderabad, Kukatpally, Old City)
- **Statutory grounding**: GHMC Act 1955 § 112 (roads), Electricity Act 2003 § 53 (streetlights), Water Act 1974 (water supply), SWM Rules 2016 (garbage), Motor Vehicles Act § 198A (pothole liability)
- **Evaluation benchmark**: 5 labeled golden test cases covering all major categories — all passing at 100% accuracy on category, severity, routing, and citation metrics

### Offline Resilience (Demo Safety Net)

The system includes a layered fallback strategy designed for live demo reliability:
1. **LLM**: Primary → Fallback model → DemoModeClient (golden JSON cache)
2. **Database**: MongoDB Atlas → InMemoryDatabase (in-process, pre-seeded)
3. **Geo APIs**: Nominatim → EXIF extraction → GPS coordinates → hardcoded city centroid

Setting `DEMO_MODE=true` in `.env` activates the full golden cache pipeline — the complete 8-node agent runs end-to-end with zero network calls, zero quota consumption, and deterministic outputs every time.

---

## 3. Evaluation Results

```
CIVICTRIAGE AGENT EVALUATION BENCHMARK (A30)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Category Classification Accuracy:  100.0%  (5/5)
  Severity Tier Agreement (Hybrid):   100.0%  (5/5)
  Jurisdictional Routing Accuracy:    100.0%  (5/5)
  Legal/Charter Citation Rate:        100.0%  (5/5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Test suite: 40 / 40 unit + integration tests passing.


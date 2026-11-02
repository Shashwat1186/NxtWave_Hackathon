# CivicTriage — Official 3-Minute Hackathon Demo Script

> **Target Audience:** Hackathon Judges & Technical Evaluators  
> **Evaluation Pillars:** Live Demo & Robustness (30 pts) · AI Reasoning & Agentic Execution (25 pts) · Impact & USP (25 pts) · Technical Depth (20 pts)  
> **Live URLs:** Frontend → `https://frontend-kappa-seven-ar0aabmczr.vercel.app` | Backend → `https://backend-peach-xi-25.vercel.app`

---

## ⏱️ Demo Timeline Overview (Total: 3 Minutes)

| Timestamp | Phase | What to Show on Screen | Key Talking Point / Value Proposition |
|-----------|-------|------------------------|---------------------------------------|
| **0:00 – 0:30** | **The Civic Problem & USP** | `SubmitPage` (Mobile UI) | 23 lakh+ annual grievances, 68% misrouted, 11,000+ road fatalities/year. CivicTriage replaces manual routing with an autonomous 8-node LangGraph triage agent with GPS-based multi-city routing. |
| **0:30 – 1:25** | **Scenario 1: Live Triage & SSE** | Click **Preset 1 (Pothole)** → `ProgressPage` | Live SSE stream showing all 8 nodes executing in real-time. Automatic GPS city detection, deterministic rule-engine routing, and multimodal perception — no polling. |
| **1:25 – 2:05** | **Issue Deep Dive & Explainability** | `IssuePage` | Mathematical 0–100 score breakdown (not black-box LLM), statutory citation, generated legal complaint, clustered report merging, and immutable 8-step audit trace. |
| **2:05 – 2:40** | **Public Dashboard & GIS Mapping** | `DashboardPage` | Real-time Leaflet map with geo-clustered severity markers (clustered into one pin per issue) and authority accountability leaderboard. |
| **2:40 – 3:00** | **Autonomous SLA Escalation** | `AdminPage` → **Trigger SLA Sweep** | Autonomous sweep agent escalates overdue tickets from Tier 1 (Ward Engineer) to Tier 2 (Zonal Commissioner) and publicly flags the department with a **"FLAGGED BREACH"** badge. |

---

## 🎬 Step-by-Step Demo Walkthrough

### Act 1: The Citizen Experience & Multimodal Capture (0:00 – 0:30)
1. **Open the Live Frontend:** Navigate to `https://frontend-kappa-seven-ar0aabmczr.vercel.app` (or `http://localhost:5173` locally).
2. **Highlight Multimodal Intake Channels:**
   - HTML5 camera capture and browser voice recording (`MediaRecorder` with multilingual transcription).
   - Automatic GPS geo-tagging via browser Geolocation API with EXIF / Nominatim landmark fallback.
   - **Emphasise:** The GPS coordinates automatically determine the *city* (Bengaluru, Mumbai, Delhi, Chennai, Hyderabad, Pune, Kolkata, etc.) and from there the *correct municipal body and department*, with no manual city selection required.
3. **Trigger Scenario 1:**
   - Under **Quick Demo Scenarios**, click **"Critical Pothole (Main Road)"**.
   - The form instantly populates with real Jubilee Hills Road 36 coordinates (17.4234°N, 78.4154°E — near Apollo Hospital, Hyderabad) and a detailed description.
   - Click **"Dispatch to CivicTriage Graph →"**.

### Act 2: Live Agentic Graph Execution via SSE (0:30 – 1:25)
1. The screen redirects to `/reports/{id}/progress`.
2. **Highlight the Live SSE Stream:**
   - Point to the pulsing **"Live SSE Stream"** indicator — zero polling, pure server-sent events.
   - Walk through all 8 nodes executing sequentially with millisecond telemetry:
     - `intake_guard` → Filters spam/memes; confirms civic relevance and media type.
     - `perceive` → Gemini 2.0 Flash Vision extracts pothole dimensions, road class (arterial), and hazard markers from the image. Gemini 1.5 Flash is the automatic failover model.
     - `geo_resolver` → Overpass/Nominatim reverse geocoding locates Apollo Hospital within 180 m, classifying this as an arterial road with critical institution proximity.
     - `deduplicator` → 500 m spatial MongoDB 2dsphere query + 768-dimensional `text-embedding-004` cosine similarity check. Duplicate reports are merged into the existing cluster; the cluster weight is incremented rather than a new ticket being created.
     - `severity_scorer` → **Deterministic Hybrid Rubric.** LLM extracts physical features; pure Python code computes: `Hazard Weight (35) + Arterial Road (20) + Hospital Proximity (20) + Cluster Bonus (10) = 85/100 → Critical`.
     - `authority_router` → **GPS-based city detection first** via `lookup_city_from_coords`. Coordinates map to Hyderabad → 25-rule Python rule engine queries MongoDB `routing_rules` by `{category, subtype, asset_type}` → matches GHMC Roads & Buildings as the primary authority. Routing happens to the *correct city* department, not a hardcoded fallback.
     - `critic` → Autonomous verification loop; if confidence < 85%, forces upstream re-perception or re-routing.
     - `dispatcher` → LLM-generated formal complaint letter citing GHMC Act 1955, SLA deadline computed as `now + 4 hours`, ticket persisted with multi-channel dispatch events (officer portal, mock email, webhook, external portal adapter).

### Act 3: Auditability & Legal Grounding (1:25 – 2:05)
1. The page automatically redirects to `/issues/{issue_id}`.
2. **Showcase Key Features:**
   - **Triage Severity Index:** Point out the 85/100 score dial and the itemized factor breakdown card (Hazard, Road Class, Proximity, Cluster Bonus, Age Penalty).
   - **Citizen Confirmation Button:** Click **"Confirm Issue"** to demonstrate instant cluster weight incrementation and priority score recalculation.
   - **Clustered Reports View:** Show that all related citizen reports are merged into a single issue card — no duplicate tickets flooding the admin console.
   - **Statutory Complaint Notice:** Show the LLM-generated formal letter citing Section 112 GHMC Act 1955 and click **"Copy Notice"**.
   - **Immutable Audit Trace:** Scroll down to show all 8 execution steps with millisecond timestamps, node summaries, and JSON payloads — full auditability, zero black-box reasoning.

### Act 4: Public Accountability & GIS Dashboard (2:05 – 2:40)
1. Click **"Public Dashboard"** in the navigation bar.
2. **Demonstrate:**
   - Aggregate stats: Total Reports, Active Triage, Critical Priority, Resolved.
   - **Interactive Leaflet Map:** Pan/zoom across Hyderabad; multiple reports on the same issue appear as a **single clustered marker** (not scattered pins), demonstrating the deduplication pipeline. Click the red critical marker to inspect the popup card. Filter by category (Road Damage, Water Leak, Garbage, etc.).
   - **Authority Accountability Leaderboard:** Live departmental performance scores and resolution rates — public-facing pressure on departments.

### Act 5: Autonomous SLA Escalation Sweep (2:40 – 3:00)
1. Navigate to **"Admin Console"** (`/admin`).
2. Show the active tickets table with Tier 1 (Ward Engineer) assignments, SLA deadlines, and the merged cluster counts.
3. Click the red **"⚡ Trigger SLA Escalation Sweep"** button.
4. **The "Wow" Moment:**
   - The scheduled background SLA agent evaluates all active tickets.
   - Overdue tickets are automatically escalated from **Tier 1 (Ward Engineer) → Tier 2 (Zonal Commissioner)**.
   - The department is branded with a pulsing **"FLAGGED BREACH"** badge on both the admin console and the public leaderboard — transparent civic accountability.

---

## 🌐 Live Deployed URLs

| Component | URL | Status |
|---|---|---|
| **Frontend Application** | `https://frontend-kappa-seven-ar0aabmczr.vercel.app` | ✅ Live |
| **Backend FastAPI API** | `https://backend-peach-xi-25.vercel.app` | ✅ Live |
| **Health Check** | `https://backend-peach-xi-25.vercel.app/health` | ✅ `{"status":"ok"}` |
| **API via Frontend Proxy** | `https://frontend-kappa-seven-ar0aabmczr.vercel.app/api/health` | ✅ Live Proxy |

> **Note for Judges:** Vercel Deployment Protection is enabled on the personal account. If a login prompt appears, disable it via Vercel Dashboard → Project Settings → Deployment Protection → set to **Disabled**.

---

## 🧪 4 Pre-Seeded Demo Presets

| # | Scenario | Coordinates | Expected Routing |
|---|---|---|---|
| 1 | Critical Pothole (Main Road) | 17.4234°N, 78.4154°E — Jubilee Hills, Hyderabad | GHMC Roads & Buildings, Tier 1, SLA 4h |
| 2 | Pressurized Water Main Rupture | 17.3850°N, 78.4867°E — Banjara Hills, Hyderabad | HMWS&SB Water Supply, Tier 1, SLA 4h |
| 3 | Dark Corridor Live-Wire Hazard | 17.4400°N, 78.3489°E — Madhapur, Hyderabad | TSSPDCL Electrical, Tier 1, SLA 4h |
| 4 | Toxic Dumpster Burning | 17.3616°N, 78.4747°E — Tolichowki, Hyderabad | GHMC Sanitation, Tier 2, SLA 24h |

---

## 💡 Key Defenses for Judge Q&A

**Q: Why not let the LLM output the severity score directly?**  
> *"LLM hallucinations in severity scoring cause erratic prioritization and legal liability. We use a **hybrid pattern**: the multimodal Gemini 2.0 Flash LLM extracts objective physical observations (pothole depth, water pressure, damage features), while an auditable, deterministic Python rubric computes the final 0–100 score from road classification, hospital proximity, and cluster size. The LLM cannot alter the math — only feed it inputs."*

**Q: How does GPS routing ensure the correct city and department?**  
> *"The `authority_router` node first calls `lookup_city_from_coords(lat, lon)`, which matches GPS coordinates against bounding-box regions for 10+ Indian cities (Bengaluru, Mumbai, Delhi, Chennai, Hyderabad, Pune, Kolkata, etc.). The resolved city determines which `CITY_DEPARTMENT_REGISTRY` entry is queried. From there, a 25-rule Python rule engine matches `{category, subtype, asset_type}` to the correct municipal department — BBMP for Bengaluru roads, BMC for Mumbai water, GHMC for Hyderabad, MCD for Delhi, and so on. Hyderabad is only a last-resort default if GPS is unavailable."*

**Q: How do you handle duplicate citizen reports?**  
> *"The `deduplicator` node executes a 2-stage check: (1) a spatial geo-radius query (500 m via MongoDB 2dsphere `$nearSphere` index) to find nearby open issues, followed by (2) cosine similarity over 768-dimensional `text-embedding-004` vector embeddings of the issue descriptions. Reports matching both thresholds are merged into the existing cluster — the cluster weight increments, boosting the priority score. No duplicate ticket is created, so the admin console shows one unified issue instead of 50 scattered duplicates."*

**Q: How does the system handle intermittent connectivity or model API downtime?**  
> *"CivicTriage has 3 fault-tolerance layers: (1) `DEMO_MODE=true` offline replay cache for judge demos with no live API key; (2) Dual MongoDB Atlas + In-Memory database fallback; and (3) Primary Gemini 2.0 Flash → automatic failover to Gemini 1.5 Flash with exponential backoff. The system never goes down mid-pipeline."*

**Q: How do you prevent department-level gaming of the public leaderboard?**  
> *"The SLA breach flag is set autonomously by the server-side sweep agent — departments cannot self-clear it. It requires a verifiable `updated_at` timestamp update with matching status change (open → resolved) to remove the `is_publicly_flagged` marker. All status changes are appended to the immutable `status_history` array in the ticket document."*

# CivicTriage — Official 3-Minute Hackathon Demo Script

> **Target Audience:** Hackathon Judges & Technical Evaluators  
> **Evaluation Pillars:** Live Demo & Robustness (30 pts) · AI Reasoning & Agentic Execution (25 pts) · Impact & USP (25 pts) · Technical Depth (20 pts)

---

## ⏱️ Demo Timeline Overview (Total: 3 Minutes)

| Timestamp | Phase | What to Show on Screen | Key Talking Point / Value Proposition |
|-----------|-------|------------------------|---------------------------------------|
| **0:00 – 0:35** | **The Civic Problem & USP** | `SubmitPage` (Mobile UI) | Traditional grievance portals are black holes. CivicTriage replaces manual routing with an 8-node LangGraph autonomous triage agent. |
| **0:35 – 1:30** | **Scenario 1: Live Triage & SSE** | Click **Preset 1 (Pothole)** → `ProgressPage` | Live SSE stream showing all 8 LangGraph nodes executing in real-time with zero polling. Multimodal perception + deterministic scoring. |
| **1:30 – 2:10** | **Issue Deep Dive & Explainability** | `IssuePage` | Mathematical score breakdown (not black-box LLM), RAG citations to Section 112 GHMC Act 1955, and generated legal complaint notice. |
| **2:10 – 2:40** | **Public Dashboard & GIS Mapping** | `DashboardPage` | Real-time Leaflet map with geo-clustered severity markers and authority accountability leaderboard. |
| **2:40 – 3:00** | **Scenario 2: Autonomous SLA Sweep** | `AdminPage` → **Trigger SLA Sweep** | Autonomous cron/sweep agent detects overdue ticket, escalates to Tier 2 (Zonal Commissioner), and publicly flags department for SLA breach. |

---

## 🎬 Step-by-Step Demo Walkthrough

### Act 1: The Citizen Experience & 1-Click Multimodal Capture (0:00 – 0:35)
1. **Open Frontend:** Navigate to `http://localhost:5173`.
2. **Highlight Mobile Capture Features:**
   - Mention the HTML5 Camera capture and browser voice note recording (`MediaRecorder`).
   - Mention automatic GPS geo-tagging with EXIF / Nominatim landmark fallback.
3. **Trigger Scenario 1:**
   - Under **Quick Demo Scenarios**, click **"Critical Pothole (Main Road)"**.
   - Notice the form instantly populates with real Jubilee Hills Road 36 coordinates (adjacent to Apollo Hospital) and detailed description.
   - Click **"Dispatch to CivicTriage Graph →"**.

### Act 2: Live Agentic Graph Execution via SSE (0:35 – 1:30)
1. The screen redirects to `/reports/{id}/progress`.
2. **Highlight the Live Stream:**
   - Point to the **"Live SSE Stream"** pulsing indicator.
   - Walk through the nodes executing sequentially:
     - `intake_guard`: Filters spam/memes and confirms civic relevance.
     - `perceive`: Multimodal vision model extracts dimensions, road class, and hazard markers.
     - `geo_resolver`: Resolves Overpass POIs (locates Apollo Hospital within 180m).
     - `deduplicator`: Spatial 500m radius query + vector embedding cosine similarity check.
     - `severity_scorer`: **Deterministic Hybrid Rubric**. The LLM extracts features, but mathematical code computes `Hazard (35) + Arterial Road (20) + Hospital Proximity (20) = 85/100 (Critical)`.
     - `authority_router`: RAG over municipal knowledge base retrieves GHMC Roads & Buildings.
     - `critic`: Autonomous verification loop ensuring evidence supports routing before dispatch.
     - `dispatcher`: Generates formal complaint letter and calculates 4-hour SLA deadline.

### Act 3: Auditability & Legal Grounding (1:30 – 2:10)
1. The page automatically redirects to `/issues/{issue_id}`.
2. **Showcase Key Features:**
   - **Triage Severity Index:** Point out the 85/100 score and the factor breakdown card.
   - **Citizen Confirmation Button:** Click **"Confirm Issue"** to demonstrate instant cluster weight incrementation.
   - **Statutory Charter Citations:** Point to the RAG citation citing **Section 112 GHMC Act 1955** and **Citizen Charter 2024**.
   - **Official Generated Complaint:** Show the formal legal complaint text and click **"Copy Notice"**.
   - **Immutable Audit Trace:** Scroll down to show all 8 execution steps with millisecond timestamps and JSON payloads.

### Act 4: Public Accountability & GIS Dashboard (2:10 – 2:40)
1. Click **"Public Dashboard"** in the navigation bar.
2. **Demonstrate:**
   - Aggregate grievance stats: Total Reports, Active Triage, Critical Priority, and Resolved.
   - **Interactive Leaflet Map:** Pan and zoom across Hyderabad; click on the red critical circle marker to inspect the popup card. Filter by category (e.g. Water Leak vs Road Damage).
   - **Authority Leaderboard:** Shows live departmental performance and resolution rates.

### Act 5: Autonomous SLA Escalation Sweep (2:40 – 3:00)
1. Navigate to **"Admin Console"** (`/admin`).
2. Show the active tickets table showing Tier 1 (Ward Engineer) assignments and SLA deadlines.
3. Click the red **"⚡ Trigger SLA Escalation Sweep"** button.
4. **The "Wow" Moment:**
   - The scheduled background SLA agent evaluates all active tickets.
   - Overdue tickets are automatically escalated from Tier 1 (Ward Engineer) to Tier 2 (Zonal Commissioner).
   - The department is branded with a pulsing **"FLAGGED BREACH"** badge both on the admin console and the public leaderboard.

---

## 💡 Key Defenses for Judge Q&A

**Q: Why not let the LLM output the severity score directly?**  
> *"LLM hallucinations in severity scoring cause erratic prioritization and liability. We use a **hybrid pattern**: the multimodal LLM extracts objective physical observations (pothole depth, water pressure), while an auditable, deterministic mathematical rubric calculates the score based on road classification, hospital proximity, and cluster size."*

**Q: How does the system handle intermittent connectivity or model API downtime?**  
> *"CivicTriage is built with 3 layers of fault tolerance: (1) `DEMO_MODE=true` offline replay cache, (2) Dual MongoDB Atlas + In-Memory database fallback, and (3) Primary-to-secondary LLM automatic model failover with exponential backoff."*

**Q: How do you prevent duplicate citizen reports from spamming departments?**  
> *"The `deduplicator` node executes a 2-stage verification: first, a spatial geo-radius query (500m via MongoDB 2dsphere index), followed by cosine similarity over vector embeddings of the issue descriptions. Matching reports are merged into a cluster, which boosts the issue's priority score rather than creating redundant tickets."*


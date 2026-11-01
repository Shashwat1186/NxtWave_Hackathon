# Problem Statement — CivicTriage

---

## 1. Target Issue & Context

### The Civic Grievance Black Hole

Every day, millions of Indians encounter broken infrastructure — a crater-sized pothole outside a hospital, a burst water main flooding three lanes, a dangling live wire on a dark pedestrian walkway. They want to report it. But the system designed to receive those reports is itself broken.

**The current civic grievance ecosystem suffers from four compounding failures:**

| Failure | Real-World Consequence |
|---|---|
| **Wrong department routing** | A water leak complaint lands with the Roads department; it sits unacknowledged for weeks while the pipe continues to burst. HMWSSB never receives it. |
| **No deduplication** | 47 citizens report the same pothole on MG Road. 47 separate tickets are created, flooding officer inboxes with noise and burying the priority signals. |
| **Zero transparency** | Citizen submits a report. Three weeks later: silence. No acknowledgement, no status, no authority name, no SLA, no accountability. |
| **Friction overload** | Portals require desktop browsers, document uploads, ward selection from 150-item dropdowns, and a registered user account — just to report a cracked footpath. |

The consequence: **citizens stop reporting**. Issues fester. Infrastructure degrades silently. Accountability collapses.

### Scale of the Problem

- India has **4,500+ Urban Local Bodies** managing roads, water, streetlights, and sanitation across 640 districts.
- The Ministry of Housing & Urban Affairs' own **CPGRAMS** platform received **23 lakh+ grievances in 2023**, with a median resolution time exceeding **21 days** — the majority misrouted at least once.
- A 2024 study of 12 Indian cities found that **68% of filed civic grievances never reached the jurisdictionally responsible authority on the first attempt** due to manual classification errors.
- **Pothole-related road accidents** account for roughly **11,000 deaths per year** in India (MoRTH 2023). The average pothole persists for **26 days** after reporting when no SLA is enforced.

### Root Technical Cause

Legacy systems use:
1. **Keyword-matching or citizen-selected dropdown categories** — easily wrong, frequently gamed.
2. **Manual officer assignment** — creating bottlenecks, bias, and jurisdictional disputes.
3. **No cross-report correlation** — individual complaints are invisible to the aggregate signal they form.
4. **No statutory grounding** — departments ignore complaints because there is no formal notice with legal weight.

---

## 2. Target Audience

CivicTriage addresses three distinct groups who are directly impacted:

### Primary: Urban Citizens
Any resident or commuter who encounters deteriorating civic infrastructure:
- **Daily commuters** on arterial roads with potholes or unsafe streetlights
- **Residents** facing water supply interruptions from burst mains
- **Neighbourhood communities** dealing with persistent garbage overflow or sewage flooding
- **Differently-abled individuals** and elderly residents for whom footpath encroachments are safety hazards
- **Emergency service corridors** (hospitals, fire stations) where road damage creates life-safety risks

These citizens are currently underserved by existing complaint portals because:
- Portals require high digital literacy
- Evidence submission is cumbersome
- There is no feedback loop post-submission
- Their reports are silently misrouted with no recourse

### Secondary: Municipal Officers & Engineers
Ward-level engineers and department heads at Urban Local Bodies (ULBs) who:
- Receive hundreds of poorly-categorized, duplicated complaints daily
- Struggle to prioritize critical-path issues (hospital routes, live wires) from routine requests
- Have no automatic SLA enforcement mechanism
- Cannot easily escalate to higher tiers (Zonal, District, State) when deadlines are missed

CivicTriage directly reduces their triage burden by delivering **pre-classified, pre-prioritized, geo-resolved tickets** into their inbox.

### Tertiary: Civil Society & Accountability Monitors
- NGOs, RWAs (Resident Welfare Associations), and journalists who track municipal accountability
- Citizens' right-to-information (RTI) filers seeking documented evidence of infrastructure neglect
- State government monitoring cells conducting SLA compliance audits

The public dashboard and formal legal complaint generation directly serve this audience.

---

## Track Alignment

**Track:** AI in Governance / Smart City Infrastructure  
**Primary SDG Alignment:** SDG 11 (Sustainable Cities and Communities), SDG 16 (Peace, Justice, and Strong Institutions)  
**Regulatory Grounding:** GHMC Act 1955 § 112, Motor Vehicles Act § 198A, Electricity Act 2003 § 53, SWM Rules 2016, Disaster Management Act 2005, IRC:SP:20 road maintenance codes


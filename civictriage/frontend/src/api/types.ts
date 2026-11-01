/**
 * frontend/src/api/types.ts
 * =========================
 * TypeScript types mirroring backend Pydantic schemas (models/schemas.py).
 * Keep in sync with any schema changes on the backend.
 */

// ── Enums ──────────────────────────────────────────────────────────────────

export type IssueCategory =
  | "road_damage"
  | "water_leak"
  | "sewage"
  | "garbage"
  | "streetlight"
  | "pollution"
  | "encroachment"
  | "tree_hazard"
  | "flood"
  | "other";

export type SeverityTier = "critical" | "high" | "medium" | "low";

export type ReportStatus =
  | "queued"
  | "processing"
  | "merged"
  | "spawned"
  | "rejected"
  | "human_review"
  | "failed";

export type IssueStatus =
  | "open"
  | "assigned"
  | "in_progress"
  | "resolved"
  | "escalated"
  | "closed";

export type TicketStatus =
  | "open"
  | "acknowledged"
  | "in_progress"
  | "resolved"
  | "escalated"
  | "closed";

// ── Geo ───────────────────────────────────────────────────────────────────

export interface GeoPoint {
  type: "Point";
  coordinates: [number, number]; // [longitude, latitude]
}

// ── API Responses ─────────────────────────────────────────────────────────

export interface ReportSubmitResponse {
  report_id: string;
  stream_url: string;
  status: ReportStatus;
  message: string;
}

export interface ScoreBreakdown {
  hazard_weight: number;
  road_class_weight: number;
  proximity_bonus: number;
  cluster_bonus: number;
  age_penalty: number;
  total: number;
  tier: SeverityTier;
}

export interface IssueOut {
  _id: string;
  category: IssueCategory;
  location: GeoPoint;
  address?: string;
  ward?: string;
  status: IssueStatus;
  report_count: number;
  priority_score: number;
  score_breakdown?: ScoreBreakdown;
  severity_tier: SeverityTier;
  created_at: string; // ISO 8601
  updated_at: string;
  trace?: TraceStep[];
  ticket_id?: string;
  // ── Rule-Based Routing fields ────────────────────────────────────────────
  department_id?: string;
  department_name?: string;
  routing_rule_id?: string;
  routing_confidence?: number;
  routing_subtype?: string;
  routing_asset_type?: string;
  routing_jurisdiction?: string;
  routing_requires_human_review?: boolean;
  source_document_ids?: string[];
}

export interface IssueListOut {
  items: IssueOut[];
  total: number;
  page: number;
  page_size: number;
}

export interface DashboardStats {
  total_reports: number;
  open_issues: number;
  resolved_issues: number;
  critical_issues: number;
  avg_resolution_hours?: number;
  top_categories: Array<{ category: IssueCategory; count: number }>;
}

export interface AuthorityLeaderboardEntry {
  authority_id: string;
  authority_name: string;
  total_tickets: number;
  resolved_tickets: number;
  avg_resolution_hours?: number;
  sla_breach_count: number;
  score: number;
}

// ── Rule-Based Routing Engine types ──────────────────────────────────────

export interface Department {
  department_id: string;
  name: string;
  short_name: string;
  tier: number;
  categories: IssueCategory[];
  contact_email?: string;
  contact_webhook?: string | null;
  escalation_parent_id?: string | null;
  sla_hours_default: number;
  is_active: boolean;
  description?: string;
}

export interface RoutingRule {
  rule_id: string;
  name: string;
  category: IssueCategory;
  subtype: string;
  asset_type: string;
  department_id: string;
  jurisdiction_type: string;
  priority: number;
  sla_hours: number;
  requires_human_review: boolean;
  source_document_ids: string[];
  routing_justification: string;
  is_active: boolean;
}

export interface SourceDocument {
  doc_id: string;
  title: string;
  section: string;
  url: string;
  authority: string;
  description: string;
}

export interface StatusEvent {
  event_type: string;
  issue_id?: string | null;
  ticket_id?: string;
  department_id?: string;
  actor: string;
  old_status?: string;
  new_status: string;
  issue_status?: string;
  note?: string | null;
  timestamp: string;
}

// ── SSE / Progress ────────────────────────────────────────────────────────

export interface VisualObservation {
  issue_type: IssueCategory;
  damage_features: string[];
  hazard_indicators: string[];
  estimated_area_sqm?: number | null;
  confidence: number;
  raw_description: string;
  image_matches_description?: boolean;
  mismatch_reason?: string | null;
}

export interface PerceptionOutput {
  visual?: VisualObservation;
  combined_description: string;
  detected_category: IssueCategory;
  confidence: number;
  model_used: string;
  image_matches_description?: boolean;
  mismatch_reason?: string | null;
}

export interface ProgressEvent {
  node: string;
  status: "running" | "done" | "error" | "retrying" | "human_review" | "complete";
  message: string;
  data?: Record<string, unknown>;
  timestamp: string;
}

// ── Trace ─────────────────────────────────────────────────────────────────

export interface TraceStep {
  node: string;
  status: "success" | "error" | "skipped";
  started_at: string;
  completed_at?: string;
  output_summary?: Record<string, unknown>;
  error?: string;
  retry_count: number;
}



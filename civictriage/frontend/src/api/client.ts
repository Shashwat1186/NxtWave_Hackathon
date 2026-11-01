/**
 * frontend/src/api/client.ts
 * ==========================
 * Typed fetch wrapper for all CivicTriage API calls.
 * All functions return typed response objects.
 * Errors throw an ApiError with detail and status.
 */

import type {
  AuthorityLeaderboardEntry,
  DashboardStats,
  Department,
  IssueListOut,
  IssueOut,
  ReportSubmitResponse,
  RoutingRule,
  StatusEvent,
} from "./types";

// In production: VITE_API_BASE_URL is set in Vercel env vars to the backend URL.
// In development: falls back to local FastAPI server.
const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

async function _fetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, options);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

// ── Reports ───────────────────────────────────────────────────────────────

/**
 * Submit a new civic issue report.
 * @param formData - FormData with optional file, description, gps_lat, gps_lng
 */
export async function submitReport(
  formData: FormData
): Promise<ReportSubmitResponse> {
  return _fetch<ReportSubmitResponse>("/reports", {
    method: "POST",
    body: formData,
  });
}

// ── Issues ────────────────────────────────────────────────────────────────

export interface ListIssuesParams {
  min_lat?: number;
  min_lng?: number;
  max_lat?: number;
  max_lng?: number;
  category?: string;
  status?: string;
  department_id?: string;
  page?: number;
  page_size?: number;
}

export async function listIssues(
  params: ListIssuesParams = {}
): Promise<IssueListOut> {
  const qs = new URLSearchParams();
  for (const [key, val] of Object.entries(params)) {
    if (val !== undefined) qs.set(key, String(val));
  }
  return _fetch<IssueListOut>(`/issues?${qs.toString()}`);
}

export async function getIssue(issueId: string): Promise<IssueOut> {
  return _fetch<IssueOut>(`/issues/${issueId}`);
}

export async function confirmIssue(
  issueId: string,
  reportId: string,
  comment?: string
): Promise<void> {
  await _fetch(`/issues/${issueId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ report_id: reportId, comment }),
  });
}

// ── Dashboard ─────────────────────────────────────────────────────────────

export async function getDashboardStats(): Promise<DashboardStats> {
  return _fetch<DashboardStats>("/dashboard/stats");
}

export async function getAuthorityLeaderboard(): Promise<
  AuthorityLeaderboardEntry[]
> {
  return _fetch<AuthorityLeaderboardEntry[]>("/authorities/leaderboard");
}

// ── Admin ─────────────────────────────────────────────────────────────────

export interface AdminTicket {
  _id: string;
  issue_id: string;
  authority_id: string;
  authority_name: string;
  tier: string | number;
  sla_deadline: string;
  status: string;
  is_publicly_flagged: boolean;
  complaint_text?: string;
  report_count?: number;
  clustered_report_ids?: string[];
  category?: string;
  address?: string;
  city?: string;
  ward?: string;
  priority_score?: number;
  severity_tier?: string;
  status_history: Array<{
    status: string;
    timestamp: string;
    note?: string;
    updated_by: string;
  }>;
  created_at: string;
  updated_at: string;
}

export async function listAdminTickets(
  adminToken: string,
  statusFilter?: string
): Promise<AdminTicket[]> {
  const qs = statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : "";
  return _fetch<AdminTicket[]>(`/admin/tickets${qs}`, {
    headers: { Authorization: `Bearer ${adminToken}` },
  });
}

export async function updateTicketStatus(
  ticketId: string,
  status: string,
  note: string,
  adminToken: string
): Promise<void> {
  await _fetch(`/admin/tickets/${ticketId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`,
    },
    body: JSON.stringify({ status, note, updated_by: "admin" }),
  });
}

export async function triggerSlaSweep(adminToken: string): Promise<unknown> {
  return _fetch("/internal/sla-sweep", {
    method: "POST",
    headers: { Authorization: `Bearer ${adminToken}` },
  });
}

// ── Rule-Based Routing & Officer Management ───────────────────────────────

export async function listDepartments(adminToken: string): Promise<Department[]> {
  return _fetch<Department[]>("/admin/departments", {
    headers: { Authorization: `Bearer ${adminToken}` },
  });
}

export async function listRoutingRules(
  adminToken: string,
  category?: string
): Promise<RoutingRule[]> {
  const qs = category ? `?category=${encodeURIComponent(category)}` : "";
  return _fetch<RoutingRule[]>(`/admin/routing-rules${qs}`, {
    headers: { Authorization: `Bearer ${adminToken}` },
  });
}

export async function getOfficerInbox(
  adminToken: string,
  departmentId?: string,
  statusFilter?: string
): Promise<{ issues: IssueOut[]; count: number; department_id?: string }> {
  const qs = new URLSearchParams();
  if (departmentId) qs.set("department_id", departmentId);
  if (statusFilter) qs.set("status_filter", statusFilter);
  const qStr = qs.toString() ? `?${qs.toString()}` : "";
  return _fetch(`/admin/officer-inbox${qStr}`, {
    headers: { Authorization: `Bearer ${adminToken}` },
  });
}

export async function updateTicketStatusV2(
  ticketId: string,
  newStatus: string,
  note: string,
  adminToken: string
): Promise<void> {
  const qs = new URLSearchParams({
    ticket_id: ticketId,
    new_status: newStatus,
    note,
    updated_by: "officer",
  });
  await _fetch(`/admin/tickets/${ticketId}/status?${qs.toString()}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${adminToken}` },
  });
}

export async function getStatusEvents(
  adminToken: string,
  issueId?: string,
  ticketId?: string
): Promise<{ events: StatusEvent[]; count: number }> {
  const qs = new URLSearchParams();
  if (issueId) qs.set("issue_id", issueId);
  if (ticketId) qs.set("ticket_id", ticketId);
  return _fetch(`/admin/status-events?${qs.toString()}`, {
    headers: { Authorization: `Bearer ${adminToken}` },
  });
}

export async function clearDatabaseRecords(
  adminToken: string,
  reseedRules = true
): Promise<{ status: string; message: string; deleted_records: Record<string, number> }> {
  return _fetch(`/admin/database/clear?reseed_rules=${reseedRules}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${adminToken}` },
  });
}


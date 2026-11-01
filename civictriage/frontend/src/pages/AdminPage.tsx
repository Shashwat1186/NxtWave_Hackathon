/**
 * frontend/src/pages/AdminPage.tsx
 * =================================
 * Password-protected Admin Panel & SLA Escalation Sweep Console.
 *
 * Capabilities:
 * - Bearer Token authentication (pre-configured with ADMIN_TOKEN)
 * - Ticket inventory inspection (Tier, Status, SLA Deadline, History)
 * - Ticket status update (PATCH /admin/tickets/{id})
 * - Autonomous SLA Escalation Sweep trigger (POST /internal/sla-sweep)
 */

import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  ShieldCheck,
  Zap,
  RefreshCw,
  AlertOctagon,
  ExternalLink,
  X,
  Lock,
  Users,
  ChevronDown,
  ChevronUp,
  Layers,
  MapPin,
} from "lucide-react";
import {
  listAdminTickets,
  updateTicketStatus,
  triggerSlaSweep,
  type AdminTicket,
} from "../api/client";

const DEFAULT_ADMIN_TOKEN = "civic-admin-secret-2026-pass";

export default function AdminPage() {
  const [token, setToken] = useState<string>(
    localStorage.getItem("civic_admin_token") || DEFAULT_ADMIN_TOKEN
  );
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [tickets, setTickets] = useState<AdminTicket[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Status update modal state
  const [selectedTicket, setSelectedTicket] = useState<AdminTicket | null>(null);
  const [newStatus, setNewStatus] = useState<string>("in_progress");
  const [updateNote, setUpdateNote] = useState<string>("");
  const [isUpdating, setIsUpdating] = useState<boolean>(false);

  // Expanded cluster details state
  const [expandedTicketId, setExpandedTicketId] = useState<string | null>(null);

  // SLA sweep state
  const [isSweeping, setIsSweeping] = useState<boolean>(false);
  const [sweepResult, setSweepResult] = useState<unknown | null>(null);

  const fetchTickets = async (authToken: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await listAdminTickets(authToken);
      setTickets(data);
      setIsAuthenticated(true);
      localStorage.setItem("civic_admin_token", authToken);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Authentication failed. Invalid admin token.");
      setIsAuthenticated(false);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (token) {
      fetchTickets(token);
    }
  }, []);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    fetchTickets(token);
  };

  const handleStatusUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedTicket) return;
    setIsUpdating(true);
    try {
      await updateTicketStatus(
        selectedTicket._id,
        newStatus,
        updateNote || `Status updated to ${newStatus} by Municipal Admin`,
        token
      );
      setSelectedTicket(null);
      setUpdateNote("");
      await fetchTickets(token);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to update ticket status");
    } finally {
      setIsUpdating(false);
    }
  };

  const handleTriggerSweep = async () => {
    setIsSweeping(true);
    setSweepResult(null);
    try {
      const res = await triggerSlaSweep(token);
      setSweepResult(res);
      await fetchTickets(token);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to trigger SLA sweep");
    } finally {
      setIsSweeping(false);
    }
  };

  // If unauthenticated or token incorrect
  if (!isAuthenticated) {
    return (
      <div className="py-20 px-4 flex items-center justify-center">
        <div className="w-full max-w-md bg-white dark:bg-slate-900 rounded-3xl shadow-xl border border-slate-200/90 dark:border-slate-800 p-8 space-y-6">
          <div className="text-center space-y-2">
            <div className="w-12 h-12 rounded-2xl bg-slate-900 dark:bg-slate-800 text-white flex items-center justify-center mx-auto shadow-md">
              <Lock className="w-6 h-6 text-blue-500" />
            </div>
            <h1 className="text-2xl font-black text-slate-900 dark:text-white">
              Municipal Admin Console
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Enter municipal authorization token to manage tickets and trigger SLA sweeps.
            </p>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-extrabold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
                Admin Bearer Token
              </label>
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="civic-admin-secret-2026-pass"
                className="w-full border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 rounded-2xl px-4 py-3 text-sm font-mono text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
                Demo token: <code className="text-slate-700 dark:text-slate-300 font-mono">civic-admin-secret-2026-pass</code>
              </p>
            </div>

            {error && (
              <div className="p-3.5 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 rounded-xl text-xs text-rose-700 dark:text-rose-300 font-bold">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading || !token}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white py-3.5 rounded-2xl font-black text-sm shadow-md transition cursor-pointer"
            >
              {isLoading ? "Verifying Token…" : "Unlock Supervisor Console"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="py-8 sm:py-12 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto space-y-6 animate-fade-in">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase font-extrabold tracking-wider px-3 py-1 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900">
              Supervisor Console
            </span>
            <span className="text-xs text-slate-500 dark:text-slate-400 font-mono">
              Role: Municipal Chief Engineer
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-black text-slate-900 dark:text-white tracking-tight mt-1">
            Grievance Dispatch &amp; SLA Management
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400">
            Audit departmental SLA performance, override statuses, and test autonomous escalation sweeps.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          {/* Autonomous SLA Sweep Trigger */}
          <button
            type="button"
            onClick={handleTriggerSweep}
            disabled={isSweeping}
            className="px-4 py-2.5 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-black shadow-md shadow-rose-500/25 transition flex items-center gap-2 cursor-pointer disabled:opacity-50 animate-pulse-glow"
          >
            <Zap className="w-4 h-4 fill-white" />
            <span>{isSweeping ? "Sweeping SLA Deadlines…" : "Trigger SLA Escalation Sweep"}</span>
          </button>

          <button
            type="button"
            onClick={() => fetchTickets(token)}
            className="px-3.5 py-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 rounded-xl text-xs font-bold transition shadow-xs flex items-center gap-1.5 cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* SLA Sweep Live Feedback Result */}
      {sweepResult && (
        <div className="p-5 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 rounded-3xl shadow-sm space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-black text-amber-900 dark:text-amber-200 text-sm flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-600 fill-amber-500" />
              <span>Autonomous SLA Sweep Finished Successfully</span>
            </span>
            <button
              type="button"
              onClick={() => setSweepResult(null)}
              className="text-amber-700 dark:text-amber-300 font-bold hover:underline text-xs"
            >
              Dismiss
            </button>
          </div>
          <pre className="bg-white dark:bg-slate-900 p-3.5 rounded-xl border border-amber-200/80 dark:border-amber-900 font-mono text-[11px] text-slate-700 dark:text-slate-300 overflow-x-auto">
            {JSON.stringify(sweepResult, null, 2)}
          </pre>
        </div>
      )}

      {/* Ticket List Table */}
      <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200/90 dark:border-slate-800 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-blue-600" />
            <h3 className="text-base font-black text-slate-900 dark:text-white">
              Active Municipal Tickets ({tickets.length})
            </h3>
          </div>
          <span className="text-xs text-slate-400">
            Auto-dispatched by LangGraph agent
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 uppercase tracking-wider font-extrabold border-b border-slate-100 dark:border-slate-800">
              <tr>
                <th className="py-3.5 px-4">Ticket &amp; Cluster</th>
                <th className="py-3.5 px-4">Grievance &amp; Location</th>
                <th className="py-3.5 px-4">Authority &amp; Tier</th>
                <th className="py-3.5 px-4">Status</th>
                <th className="py-3.5 px-4">SLA Deadline</th>
                <th className="py-3.5 px-4">Breach Status</th>
                <th className="py-3.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {tickets.length > 0 ? (
                tickets.map((t) => {
                  const isOverdue =
                    t.sla_deadline && new Date(t.sla_deadline).getTime() < Date.now();
                  const isClustered = (t.report_count ?? 1) > 1;
                  const isExpanded = expandedTicketId === t._id;

                  return (
                    <React.Fragment key={t._id}>
                      <tr className="hover:bg-slate-50/70 dark:hover:bg-slate-800/40 transition">
                        <td className="py-4 px-4 font-mono font-bold text-slate-900 dark:text-white">
                          <div className="flex items-center gap-2">
                            <span>#{t._id.slice(-6)}</span>
                          </div>
                          {isClustered ? (
                            <div className="flex items-center gap-1.5 mt-1">
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-black bg-indigo-100 text-indigo-700 dark:bg-indigo-950/70 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800">
                                <Users className="w-3 h-3" />
                                <span>{t.report_count} Reports Clubbed</span>
                              </span>
                              <button
                                type="button"
                                onClick={() => setExpandedTicketId(isExpanded ? null : t._id)}
                                className="text-[10px] font-bold text-indigo-600 dark:text-indigo-400 hover:underline flex items-center gap-0.5 cursor-pointer"
                                title="View clubbed report IDs"
                              >
                                {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                                <span>{isExpanded ? "Hide" : "Details"}</span>
                              </button>
                            </div>
                          ) : (
                            <span className="inline-block mt-1 text-[10px] font-medium text-slate-400">
                              Single Report
                            </span>
                          )}
                        </td>
                        <td className="py-4 px-4 max-w-xs">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-black uppercase tracking-wider bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200">
                              {t.category || "Civic Grievance"}
                            </span>
                            {t.city && (
                              <span className="inline-flex items-center gap-0.5 text-[10px] font-extrabold text-blue-600 dark:text-blue-400">
                                <MapPin className="w-2.5 h-2.5" />
                                {t.city}
                              </span>
                            )}
                          </div>
                          {t.address && (
                            <p className="text-[11px] text-slate-500 dark:text-slate-400 truncate mt-0.5" title={t.address}>
                              {t.address}
                            </p>
                          )}
                          {t.ward && (
                            <p className="text-[10px] text-slate-400 dark:text-slate-500">
                              {t.ward}
                            </p>
                          )}
                        </td>
                        <td className="py-4 px-4">
                          <p className="font-black text-slate-900 dark:text-white">{t.authority_name}</p>
                          <p className="text-[11px] text-slate-500 dark:text-slate-400">Tier: {t.tier}</p>
                        </td>
                        <td className="py-4 px-4">
                          <span
                            className={`px-2.5 py-1 rounded-full text-[11px] font-black capitalize ${
                              t.status === "resolved"
                                ? "bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300"
                                : t.status === "escalated"
                                ? "bg-rose-100 dark:bg-rose-950/60 text-rose-800 dark:text-rose-300"
                                : "bg-blue-100 dark:bg-blue-950/60 text-blue-800 dark:text-blue-300"
                            }`}
                          >
                            {t.status.replace("_", " ")}
                          </span>
                        </td>
                        <td className="py-4 px-4 font-mono text-[11px] text-slate-600 dark:text-slate-300">
                          {t.sla_deadline ? new Date(t.sla_deadline).toLocaleString() : "N/A"}
                          {isOverdue && t.status !== "resolved" && (
                            <span className="block text-[10px] text-rose-600 dark:text-rose-400 font-black">
                              OVERDUE
                            </span>
                          )}
                        </td>
                        <td className="py-4 px-4">
                          {t.is_publicly_flagged ? (
                            <span className="inline-flex items-center gap-1 bg-rose-600 text-white font-black px-2 py-0.5 rounded-full text-[10px] animate-pulse">
                              <AlertOctagon className="w-3 h-3" />
                              <span>FLAGGED BREACH</span>
                            </span>
                          ) : (
                            <span className="text-emerald-700 dark:text-emerald-400 text-[11px] font-bold">
                              Within SLA
                            </span>
                          )}
                        </td>
                        <td className="py-4 px-4 text-right space-x-2 whitespace-nowrap">
                          {t.issue_id && (
                            <Link
                              to={`/issues/${t.issue_id}`}
                              className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline font-bold"
                            >
                              <span>View</span>
                              <ExternalLink className="w-3 h-3" />
                            </Link>
                          )}
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedTicket(t);
                              setNewStatus(t.status === "resolved" ? "resolved" : "in_progress");
                            }}
                            className="bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 px-3 py-1 rounded-lg font-bold cursor-pointer transition"
                          >
                            Update
                          </button>
                        </td>
                      </tr>

                      {/* Expandable Clustered Reports Tray */}
                      {isExpanded && (
                        <tr className="bg-indigo-50/60 dark:bg-indigo-950/20 border-b border-indigo-100 dark:border-indigo-900/50">
                          <td colSpan={7} className="py-3 px-6 animate-fade-in">
                            <div className="space-y-2.5">
                              <div className="flex items-center justify-between flex-wrap gap-2">
                                <span className="text-xs font-black text-indigo-950 dark:text-indigo-200 flex items-center gap-1.5">
                                  <Layers className="w-3.5 h-3.5 text-indigo-600" />
                                  <span>Consolidated Incident Cluster ({t.report_count ?? 1} Citizen Reports Clubbed Into 1 Ticket)</span>
                                </span>
                                {t.issue_id && (
                                  <span className="text-[11px] text-slate-500 font-mono">
                                    Issue UID: {t.issue_id}
                                  </span>
                                )}
                              </div>
                              <p className="text-xs text-slate-600 dark:text-slate-300">
                                Deduplication identified duplicate geo-spatial complaints for this exact defect.
                                All reports are unified under this ticket to prevent redundant municipal dispatch.
                              </p>
                              <div className="flex flex-wrap items-center gap-2 pt-1">
                                <span className="text-[11px] font-extrabold uppercase text-indigo-900 dark:text-indigo-300">
                                  Clubbed Reports:
                                </span>
                                {t.clustered_report_ids && t.clustered_report_ids.length > 0 ? (
                                  t.clustered_report_ids.map((rid, idx) => (
                                    <span
                                      key={rid}
                                      className="inline-flex items-center gap-1.5 bg-white dark:bg-slate-900 border border-indigo-200 dark:border-indigo-800/80 px-2.5 py-1 rounded-lg text-[11px] font-mono shadow-xs"
                                    >
                                      <span className="w-4 h-4 rounded-full bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300 font-black text-[9px] flex items-center justify-center">
                                        {idx + 1}
                                      </span>
                                      <span className="font-bold text-slate-700 dark:text-slate-200">
                                        Report #{rid.slice(-6)}
                                      </span>
                                    </span>
                                  ))
                                ) : (
                                  <span className="text-[11px] font-mono text-slate-500">
                                    Report #{t._id.slice(-6)}
                                  </span>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-400">
                    No active tickets recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Update Ticket Status Modal */}
      {selectedTicket && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-fade-in">
          <div className="bg-white dark:bg-slate-900 rounded-3xl max-w-md w-full p-6 sm:p-8 shadow-2xl border border-slate-200/90 dark:border-slate-800 space-y-5">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-black text-slate-900 dark:text-white">
                Update Ticket #{selectedTicket._id.slice(-6)}
              </h3>
              <button
                type="button"
                onClick={() => setSelectedTicket(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Clustered Reports Notification in Modal */}
            {(selectedTicket.report_count ?? 1) > 1 && (
              <div className="p-3 bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-900 rounded-2xl text-xs text-indigo-900 dark:text-indigo-200 space-y-1">
                <p className="font-black flex items-center gap-1.5">
                  <Users className="w-3.5 h-3.5 text-indigo-600" />
                  <span>Consolidated Cluster: {selectedTicket.report_count} Reports Clubbed</span>
                </p>
                <p className="text-[11px] text-slate-600 dark:text-slate-300">
                  This ticket unifies {selectedTicket.report_count} duplicate citizen complaints for {selectedTicket.category || "this grievance"} in {selectedTicket.city || "this city"}.
                  Updating this status applies across the entire cluster and synchronizes public tracking.
                </p>
              </div>
            )}

            <form onSubmit={handleStatusUpdate} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                  Change Status
                </label>
                <select
                  value={newStatus}
                  onChange={(e) => setNewStatus(e.target.value)}
                  className="w-full border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 rounded-xl px-3.5 py-2.5 text-xs font-bold text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="in_progress">In Progress</option>
                  <option value="resolved">Resolved</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                  Audit Log Note
                </label>
                <textarea
                  value={updateNote}
                  onChange={(e) => setUpdateNote(e.target.value)}
                  placeholder="e.g. Dispatched mechanical patch unit to repair crater."
                  rows={3}
                  className="w-full border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setSelectedTicket(null)}
                  className="px-4 py-2 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 rounded-xl text-xs font-bold hover:bg-slate-50 dark:hover:bg-slate-800 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isUpdating}
                  className="px-5 py-2 bg-blue-600 text-white rounded-xl text-xs font-black hover:bg-blue-700 shadow-md cursor-pointer"
                >
                  {isUpdating ? "Saving…" : "Save Status"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

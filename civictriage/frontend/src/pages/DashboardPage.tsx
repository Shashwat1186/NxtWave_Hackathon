/**
 * frontend/src/pages/DashboardPage.tsx
 * =====================================
 * Public Civic Accountability Dashboard.
 *
 * Real-time views:
 * 1. Pan-India Grievance Metric KPI Cards
 * 2. Interactive Leaflet GIS Map with Severity Clustering
 * 3. Authority Performance & SLA Breach Leaderboard
 * 4. Filterable Recent Grievances Feed with search
 */

import React, { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  FileText,
  Clock,
  ShieldAlert,
  CheckCircle2,
  RefreshCw,
  PlusCircle,
  Search,
  Building2,
  ArrowRight,
} from "lucide-react";
import IssueMap from "../map/IssueMap";
import ReportCard from "../components/ReportCard";
import {
  getDashboardStats,
  getAuthorityLeaderboard,
  listIssues,
} from "../api/client";
import type {
  AuthorityLeaderboardEntry,
  DashboardStats,
  IssueOut,
} from "../api/types";

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [leaderboard, setLeaderboard] = useState<AuthorityLeaderboardEntry[]>([]);
  const [recentIssues, setRecentIssues] = useState<IssueOut[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [statsData, boardData, issuesData] = await Promise.all([
        getDashboardStats().catch(() => null),
        getAuthorityLeaderboard().catch(() => []),
        listIssues({ page_size: 12 }).catch(() => ({ items: [], total: 0 })),
      ]);

      if (statsData) setStats(statsData);
      if (boardData) setLeaderboard(boardData);
      if (issuesData?.items) setRecentIssues(issuesData.items);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, []);

  const filteredIssues = useMemo(() => {
    return recentIssues.filter((issue) => {
      if (categoryFilter !== "all" && issue.category !== categoryFilter) return false;
      if (statusFilter !== "all" && issue.status !== statusFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const addr = (issue.address || "").toLowerCase();
        const cat = issue.category.toLowerCase();
        const stat = (issue.status || "").toLowerCase();
        if (!addr.includes(q) && !cat.includes(q) && !stat.includes(q)) return false;
      }
      return true;
    });
  }, [recentIssues, categoryFilter, statusFilter, searchQuery]);

  return (
    <div className="py-8 sm:py-12 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto space-y-8 animate-fade-in">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase font-extrabold tracking-wider px-3 py-1 rounded-full bg-blue-100 dark:bg-blue-950/60 text-blue-800 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
              Public Accountability
            </span>
            <span className="text-xs text-slate-400 font-medium">Pan-India Municipal &amp; District Administration</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-black text-slate-900 dark:text-white tracking-tight">
            Civic Infrastructure Triage Dashboard
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400">
            Real-time transparency, automated rule-based routing, and statutory SLA monitoring.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={loadData}
            disabled={isLoading}
            className="px-4 py-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 rounded-xl text-xs font-bold shadow-xs transition flex items-center gap-1.5 cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-blue-600" : ""}`} />
            <span>Refresh</span>
          </button>
          <Link
            to="/"
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-black shadow-md shadow-blue-500/20 transition flex items-center gap-1.5"
          >
            <PlusCircle className="w-4 h-4" />
            <span>+ Report Issue</span>
          </Link>
        </div>
      </div>

      {/* Metric KPI Stat Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {/* Total Grievances */}
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/90 dark:border-slate-800 p-5 shadow-sm space-y-2">
          <div className="flex items-center justify-between text-slate-400 dark:text-slate-500">
            <span className="text-xs font-extrabold uppercase tracking-wider">Total Reports</span>
            <FileText className="w-4 h-4 text-blue-600 dark:text-blue-400" />
          </div>
          <p className="text-3xl sm:text-4xl font-black text-slate-900 dark:text-white">
            {stats?.total_reports ?? (isLoading ? "…" : 0)}
          </p>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">Ingested via multimodal AI</p>
        </div>

        {/* Active Triage */}
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/90 dark:border-slate-800 p-5 shadow-sm space-y-2">
          <div className="flex items-center justify-between text-amber-500">
            <span className="text-xs font-extrabold uppercase tracking-wider">Active Triage</span>
            <Clock className="w-4 h-4" />
          </div>
          <p className="text-3xl sm:text-4xl font-black text-amber-600 dark:text-amber-400">
            {stats?.open_issues ?? (isLoading ? "…" : 0)}
          </p>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">Open &amp; routed issues</p>
        </div>

        {/* Critical Priority */}
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/90 dark:border-slate-800 p-5 shadow-sm space-y-2">
          <div className="flex items-center justify-between text-rose-500">
            <span className="text-xs font-extrabold uppercase tracking-wider">Critical Priority</span>
            <ShieldAlert className="w-4 h-4" />
          </div>
          <p className="text-3xl sm:text-4xl font-black text-rose-600 dark:text-rose-400">
            {stats?.critical_issues ?? (isLoading ? "…" : 0)}
          </p>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">SLA ≤ 4h emergency triage</p>
        </div>

        {/* Resolved Issues */}
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/90 dark:border-slate-800 p-5 shadow-sm space-y-2">
          <div className="flex items-center justify-between text-emerald-500">
            <span className="text-xs font-extrabold uppercase tracking-wider">Resolved</span>
            <CheckCircle2 className="w-4 h-4" />
          </div>
          <p className="text-3xl sm:text-4xl font-black text-emerald-600 dark:text-emerald-400">
            {stats?.resolved_issues ?? (isLoading ? "…" : 0)}
          </p>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">
            Avg time: {stats?.avg_resolution_hours ? `${stats.avg_resolution_hours}h` : "N/A"}
          </p>
        </div>
      </div>

      {/* Map & Leaderboard Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Map Column (2 spans) */}
        <div className="lg:col-span-2 h-[540px]">
          <IssueMap height="100%" />
        </div>

        {/* Authority Accountability Leaderboard (1 span) */}
        <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200/90 dark:border-slate-800 p-6 shadow-sm flex flex-col justify-between">
          <div className="space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
              <div>
                <h3 className="text-base font-black text-slate-900 dark:text-white flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-indigo-600" />
                  <span>Authority Accountability</span>
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Live department SLA compliance
                </p>
              </div>
              <span className="text-[10px] font-extrabold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 px-2 py-0.5 rounded-full border border-indigo-200 dark:border-indigo-900">
                Autonomous SLA
              </span>
            </div>

            <div className="divide-y divide-slate-100 dark:divide-slate-800 max-h-[380px] overflow-y-auto pr-1">
              {leaderboard.length > 0 ? (
                leaderboard.map((entry) => {
                  const hasBreach = (entry.sla_breach_count || 0) > 0;
                  const resolvePercent =
                    entry.total_tickets > 0
                      ? Math.round((entry.resolved_tickets / entry.total_tickets) * 100)
                      : 100;

                  return (
                    <div key={entry.authority_id} className="py-3.5 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <h4 className="text-xs font-black text-slate-900 dark:text-white truncate max-w-[190px]">
                          {entry.authority_name}
                        </h4>
                        <span className="text-xs font-mono font-bold text-slate-700 dark:text-slate-300">
                          {entry.score.toFixed(1)} pts
                        </span>
                      </div>

                      {/* Mini resolution progress bar */}
                      <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-blue-600 h-full rounded-full"
                          style={{ width: `${resolvePercent}%` }}
                        />
                      </div>

                      <div className="flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
                        <span>
                          {entry.resolved_tickets}/{entry.total_tickets} resolved ({resolvePercent}%)
                        </span>
                        {hasBreach ? (
                          <span className="text-rose-600 dark:text-rose-400 font-extrabold bg-rose-50 dark:bg-rose-950/60 px-2 py-0.5 rounded text-[10px] animate-pulse border border-rose-200 dark:border-rose-900">
                            ⚠️ {entry.sla_breach_count} Breach (Flagged)
                          </span>
                        ) : (
                          <span className="text-emerald-700 dark:text-emerald-300 font-bold bg-emerald-50 dark:bg-emerald-950/60 px-2 py-0.5 rounded text-[10px]">
                            ✓ On-Time
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="py-12 text-center text-xs text-slate-400">
                  No authority records loaded.
                </div>
              )}
            </div>
          </div>

          <div className="pt-4 border-t border-slate-100 dark:border-slate-800">
            <Link
              to="/admin"
              className="w-full py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl text-xs font-bold transition flex items-center justify-center gap-1.5"
            >
              <span>Access Supervisor &amp; SLA Console</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
      </div>

      {/* Filterable Recent Grievance Feed */}
      <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200/90 dark:border-slate-800 p-6 sm:p-8 shadow-sm space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 className="text-lg sm:text-xl font-black text-slate-900 dark:text-white">
              Recent Triaged Grievances
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Live audit stream of complaints geo-clustered across urban wards
            </p>
          </div>

          {/* Search Input */}
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3.5 top-2.5 w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search address, category..."
              className="w-full pl-9 pr-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 dark:text-white"
            />
          </div>
        </div>

        {/* Status & Category Filters */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pt-1 border-t border-slate-100 dark:border-slate-800">
          {/* Status Filter Tabs */}
          <div className="flex items-center gap-1.5 text-xs flex-wrap">
            <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-400 mr-1">Status:</span>
            {[
              { id: "all", label: "All Statuses" },
              { id: "in_progress", label: "⏳ In Progress" },
              { id: "resolved", label: "✓ Resolved" },
            ].map((st) => (
              <button
                key={st.id}
                type="button"
                onClick={() => setStatusFilter(st.id)}
                className={`px-3 py-1.5 rounded-xl font-bold transition-all cursor-pointer ${statusFilter === st.id
                  ? st.id === "resolved"
                    ? "bg-emerald-600 text-white shadow-xs"
                    : "bg-blue-600 text-white shadow-xs"
                  : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
                  }`}
              >
                {st.label}
              </button>
            ))}
          </div>

          {/* Category Filter Pills */}
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            {[
              { id: "all", label: "All Categories" },
              { id: "road_damage", label: "🚧 Road" },
              { id: "water_leak", label: "💧 Water" },
              { id: "sewage", label: "⚠️ Sewage" },
              { id: "garbage", label: "🗑️ Sanitation" },
              { id: "streetlight", label: "💡 Streetlights" },
            ].map((cat) => (
              <button
                key={cat.id}
                type="button"
                onClick={() => setCategoryFilter(cat.id)}
                className={`px-3 py-1.5 rounded-xl font-bold transition-all cursor-pointer ${categoryFilter === cat.id
                  ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-xs"
                  : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
                  }`}
              >
                {cat.label}
              </button>
            ))}
          </div>
        </div>

        {/* Grievances Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredIssues.length > 0 ? (
            filteredIssues.map((issue) => (
              <ReportCard key={issue._id} issue={issue} />
            ))
          ) : (
            <div className="col-span-full py-16 text-center text-xs text-slate-400">
              No matching civic grievances found. Click "+ Report Issue" to add a new report.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

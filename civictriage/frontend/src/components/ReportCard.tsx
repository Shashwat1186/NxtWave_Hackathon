/**
 * frontend/src/components/ReportCard.tsx
 * ======================================
 * Compact civic grievance card for feeds and dashboard grids.
 */

import React from "react";
import { Link } from "react-router-dom";
import {
  MapPin,
  ArrowRight,
  ShieldAlert,
  AlertTriangle,
  Clock,
  CheckCircle2,
  Users,
} from "lucide-react";
import type { IssueOut, SeverityTier } from "../api/types";

interface ReportCardProps {
  issue: IssueOut;
}

const CATEGORY_EMOJIS: Record<string, string> = {
  road_damage: "🚧",
  water_leak: "💧",
  sewage: "⚠️",
  garbage: "🗑️",
  streetlight: "💡",
  pollution: "🏭",
  encroachment: "⛔",
  tree_hazard: "🌳",
  flood: "🌊",
  other: "📌",
};

const SEVERITY_BADGES: Record<
  SeverityTier,
  { badgeClass: string; icon: React.ComponentType<{ className?: string }> }
> = {
  critical: {
    badgeClass: "bg-rose-100 dark:bg-rose-950/60 text-rose-800 dark:text-rose-300 border-rose-300 dark:border-rose-800",
    icon: ShieldAlert,
  },
  high: {
    badgeClass: "bg-orange-100 dark:bg-orange-950/60 text-orange-800 dark:text-orange-300 border-orange-300 dark:border-orange-800",
    icon: AlertTriangle,
  },
  medium: {
    badgeClass: "bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 border-amber-300 dark:border-amber-800",
    icon: Clock,
  },
  low: {
    badgeClass: "bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800",
    icon: CheckCircle2,
  },
};

export default function ReportCard({ issue }: ReportCardProps) {
  const emoji = CATEGORY_EMOJIS[issue.category] || "📌";
  const sevConfig = SEVERITY_BADGES[issue.severity_tier] || SEVERITY_BADGES.low;
  const SevIcon = sevConfig.icon;

  return (
    <div
      className={`rounded-2xl border p-5 shadow-sm hover:shadow-md transition-all flex flex-col justify-between group ${
        issue.status === "resolved"
          ? "bg-emerald-50/30 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-900/60 hover:border-emerald-400 dark:hover:border-emerald-700"
          : "bg-white dark:bg-slate-900 border-slate-200/90 dark:border-slate-800 hover:border-blue-400 dark:hover:border-blue-600"
      }`}
    >
      <div className="space-y-3">
        {/* Header: Category & Severity */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <span className="text-2xl p-1.5 bg-slate-100 dark:bg-slate-800 rounded-xl">{emoji}</span>
            <div>
              <h4 className="text-sm font-black text-slate-900 dark:text-white capitalize">
                {issue.category.replace("_", " ")}
              </h4>
              <p className="text-[11px] font-mono text-slate-400">
                #{issue._id.slice(-6)}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5 flex-wrap justify-end">
            {issue.status === "resolved" ? (
              <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-black border bg-emerald-100 dark:bg-emerald-950/80 text-emerald-800 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800 shadow-xs">
                <CheckCircle2 className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
                <span>Resolved</span>
              </span>
            ) : issue.status === "in_progress" ? (
              <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-black border bg-blue-100 dark:bg-blue-950/80 text-blue-800 dark:text-blue-300 border-blue-300 dark:border-blue-800 shadow-xs">
                <Clock className="w-3 h-3 text-blue-600 dark:text-blue-400" />
                <span>In Progress</span>
              </span>
            ) : null}
            <span
              className={`flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold border capitalize ${sevConfig.badgeClass}`}
            >
              <SevIcon className="w-3 h-3" />
              <span>{issue.severity_tier}</span>
            </span>
          </div>
        </div>

        {/* Location address */}
        <div className="flex items-start gap-1.5 text-xs text-slate-600 dark:text-slate-400">
          <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
          <p className="line-clamp-2 leading-relaxed">
            {issue.address || "Urban Metropolitan Area"}
          </p>
        </div>
      </div>

      {/* Footer Metrics & Drilldown */}
      <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 font-bold text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/60 px-2 py-0.5 rounded-lg border border-blue-200 dark:border-blue-900">
            <Users className="w-3 h-3" />
            <span>{issue.report_count}</span>
          </span>
          <span className="font-mono text-[11px] text-slate-500">
            Score:{" "}
            <strong className="text-slate-800 dark:text-slate-200">
              {Math.round(
                issue.priority_score <= 1.0 && issue.priority_score > 0
                  ? issue.priority_score * 100
                  : issue.priority_score
              )}
            </strong>
          </span>
        </div>

        <Link
          to={`/issues/${issue._id}`}
          className="text-xs font-bold text-blue-600 dark:text-blue-400 group-hover:translate-x-0.5 transition-transform flex items-center gap-1 hover:underline"
        >
          <span>Inspect</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  );
}

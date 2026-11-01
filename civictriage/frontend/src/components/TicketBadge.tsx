/**
 * frontend/src/components/TicketBadge.tsx
 * =======================================
 * Jurisdictional routing badge with live SLA countdown and breach flag indicator.
 */

import React from "react";
import { Building2, Clock, AlertOctagon } from "lucide-react";

interface TicketBadgeProps {
  authorityName?: string;
  tier?: string;
  slaDeadline?: string;
  isFlagged?: boolean;
  status?: string;
}

export default function TicketBadge({
  authorityName = "Municipal Corporation Road Maintenance",
  tier = "Tier 1: Ward Engineer",
  slaDeadline,
  isFlagged = false,
  status = "open",
}: TicketBadgeProps) {
  let timeRemainingText = "Standard SLA";
  let isOverdue = false;

  if (slaDeadline) {
    const deadline = new Date(slaDeadline).getTime();
    const now = Date.now();
    const diffHours = Math.round((deadline - now) / (1000 * 60 * 60));

    if (diffHours < 0) {
      isOverdue = true;
      timeRemainingText = `Overdue by ${Math.abs(diffHours)}h`;
    } else {
      timeRemainingText = `${diffHours}h remaining`;
    }
  }

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200/90 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-slate-500">
            <Building2 className="w-3.5 h-3.5" />
            <span>Assigned Municipal Authority</span>
          </div>
          <h3 className="text-base font-black text-slate-900 dark:text-white leading-snug">
            {authorityName}
          </h3>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-xs bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 px-2.5 py-0.5 rounded-lg font-bold border border-indigo-200 dark:border-indigo-800">
              {tier}
            </span>
            <span className="text-xs bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 px-2.5 py-0.5 rounded-lg font-bold capitalize border border-slate-200 dark:border-slate-700">
              {status.replace("_", " ")}
            </span>
          </div>
        </div>

        {isFlagged ? (
          <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-black bg-rose-600 text-white animate-pulse shadow-md shadow-rose-500/30 shrink-0">
            <AlertOctagon className="w-4 h-4" />
            <span>SLA Breached (Flagged)</span>
          </span>
        ) : (
          <span
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold border shrink-0 ${
              isOverdue
                ? "bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800"
                : "bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800"
            }`}
          >
            {isOverdue ? <AlertOctagon className="w-3.5 h-3.5 text-rose-600" /> : <Clock className="w-3.5 h-3.5 text-emerald-600" />}
            <span>{timeRemainingText}</span>
          </span>
        )}
      </div>

      {slaDeadline && (
        <div className="text-xs text-slate-500 dark:text-slate-400 border-t border-slate-100 dark:border-slate-800 pt-3 flex items-center justify-between">
          <span className="flex items-center gap-1">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>Statutory SLA Deadline:</span>
          </span>
          <span className="font-mono font-bold text-slate-800 dark:text-slate-200">
            {new Date(slaDeadline).toLocaleString()}
          </span>
        </div>
      )}
    </div>
  );
}

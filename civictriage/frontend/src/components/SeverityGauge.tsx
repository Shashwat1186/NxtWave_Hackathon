/**
 * frontend/src/components/SeverityGauge.tsx
 * =========================================
 * Visual priority score meter detailing the deterministic scoring rubric.
 */

import React from "react";
import { ShieldAlert, AlertTriangle, Clock, CheckCircle2, Info } from "lucide-react";
import type { ScoreBreakdown, SeverityTier } from "../api/types";

interface SeverityGaugeProps {
  score: number;
  tier: SeverityTier;
  breakdown?: ScoreBreakdown;
  size?: "sm" | "md" | "lg";
}

const TIER_CONFIG: Record<
  SeverityTier,
  {
    label: string;
    badgeClass: string;
    bgGradient: string;
    textColor: string;
    icon: React.ComponentType<{ className?: string }>;
  }
> = {
  critical: {
    label: "Critical Priority",
    badgeClass: "bg-rose-100 dark:bg-rose-950/60 text-rose-800 dark:text-rose-300 border-rose-300 dark:border-rose-800",
    bgGradient: "from-rose-500 to-red-600",
    textColor: "text-rose-600 dark:text-rose-400",
    icon: ShieldAlert,
  },
  high: {
    label: "High Priority",
    badgeClass: "bg-orange-100 dark:bg-orange-950/60 text-orange-800 dark:text-orange-300 border-orange-300 dark:border-orange-800",
    bgGradient: "from-amber-500 to-orange-600",
    textColor: "text-orange-600 dark:text-orange-400",
    icon: AlertTriangle,
  },
  medium: {
    label: "Medium Priority",
    badgeClass: "bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 border-amber-300 dark:border-amber-800",
    bgGradient: "from-yellow-400 to-amber-500",
    textColor: "text-amber-600 dark:text-amber-400",
    icon: Clock,
  },
  low: {
    label: "Low Priority",
    badgeClass: "bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800",
    bgGradient: "from-emerald-400 to-teal-500",
    textColor: "text-emerald-600 dark:text-emerald-400",
    icon: CheckCircle2,
  },
};

export default function SeverityGauge({
  score,
  tier,
  breakdown,
}: SeverityGaugeProps) {
  const config = TIER_CONFIG[tier] || TIER_CONFIG.low;
  const Icon = config.icon;
  // Priority score is normalized 0.0-1.0 in DB; scale to 0-100 for display
  const rawScore =
    breakdown?.total !== undefined && breakdown.total > 0
      ? breakdown.total
      : score <= 1.0 && score > 0
        ? score * 100
        : score;
  const clampedScore = Math.min(100, Math.max(0, Math.round(rawScore)));

  return (
    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/90 dark:border-slate-800 p-6 shadow-sm space-y-5">
      {/* Header & Score Display */}
      <div className="flex items-center justify-between">
        <div>
          <span className="text-[11px] uppercase tracking-wider font-extrabold text-slate-400 dark:text-slate-500">
            Triage Severity Index
          </span>
          <div className="flex items-baseline gap-2 mt-1">
            <span className={`text-4xl font-black tracking-tight ${config.textColor}`}>
              {clampedScore}
            </span>
            <span className="text-slate-400 dark:text-slate-500 font-bold text-sm">/ 100</span>
          </div>
        </div>

        <span
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-black border ${config.badgeClass} capitalize shadow-xs`}
        >
          <Icon className="w-4 h-4" />
          <span>{config.label}</span>
        </span>
      </div>

      {/* Progress Bar */}
      <div>
        <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-3.5 overflow-hidden p-0.5 shadow-inner">
          <div
            className={`h-full rounded-full bg-gradient-to-r ${config.bgGradient} transition-all duration-1000 ease-out`}
            style={{ width: `${clampedScore}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-slate-400 dark:text-slate-500 mt-1.5 font-mono font-bold">
          <span>0 (Low)</span>
          <span>40 (Med)</span>
          <span>60 (High)</span>
          <span>80+ (Critical)</span>
        </div>
      </div>

      {/* Deterministic Rubric Breakdown */}
      {breakdown && (
        <div className="border-t border-slate-100 dark:border-slate-800 pt-4 space-y-3">
          <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400 font-bold">
            <span className="flex items-center gap-1">
              <Info className="w-3.5 h-3.5 text-blue-500" />
              <span>Auditable Rubric Components</span>
            </span>
            <span className="text-[10px] font-extrabold text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/60 px-2 py-0.5 rounded-md border border-blue-200 dark:border-blue-900">
              Deterministic Math
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex justify-between items-center bg-slate-50 dark:bg-slate-800/60 p-2.5 rounded-xl border border-slate-100 dark:border-slate-800">
              <span className="text-slate-600 dark:text-slate-400">Hazard Base:</span>
              <span className="font-mono font-bold text-slate-900 dark:text-white">
                +{breakdown.hazard_weight}
              </span>
            </div>
            <div className="flex justify-between items-center bg-slate-50 dark:bg-slate-800/60 p-2.5 rounded-xl border border-slate-100 dark:border-slate-800">
              <span className="text-slate-600 dark:text-slate-400">Road Class:</span>
              <span className="font-mono font-bold text-slate-900 dark:text-white">
                +{breakdown.road_class_weight}
              </span>
            </div>
            <div className="flex justify-between items-center bg-slate-50 dark:bg-slate-800/60 p-2.5 rounded-xl border border-slate-100 dark:border-slate-800">
              <span className="text-slate-600 dark:text-slate-400">Hospital / School Proximity:</span>
              <span className="font-mono font-bold text-slate-900 dark:text-white">
                +{breakdown.proximity_bonus}
              </span>
            </div>
            <div className="flex justify-between items-center bg-slate-50 dark:bg-slate-800/60 p-2.5 rounded-xl border border-slate-100 dark:border-slate-800">
              <span className="text-slate-600 dark:text-slate-400">Geo Cluster Bonus:</span>
              <span className="font-mono font-bold text-slate-900 dark:text-white">
                +{breakdown.cluster_bonus}
              </span>
            </div>
            {breakdown.age_penalty > 0 && (
              <div className="col-span-2 flex justify-between items-center bg-amber-50 dark:bg-amber-950/40 p-2.5 rounded-xl border border-amber-200 dark:border-amber-900">
                <span className="text-amber-800 dark:text-amber-300 font-bold">Age Escalation Penalty:</span>
                <span className="font-mono font-black text-amber-900 dark:text-amber-200">
                  +{breakdown.age_penalty}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * frontend/src/components/ProgressTracker.tsx
 * ============================================
 * Live agent pipeline progress visualization with real-time SSE stream.
 *
 * Features:
 * - 8 Agent Nodes with Lucide icons, glowing animated active states, and completion ticks
 * - Interactive telemetry drawer displaying live extracted values (road class, POIs, score, citations)
 * - Completion celebratory banner with direct navigation
 */

import React from "react";
import {
  Shield,
  Eye,
  Compass,
  GitMerge,
  Scale,
  Building2,
  CheckCircle2,
  FileCheck2,
  Loader2,
  AlertTriangle,
  ArrowRight,
  Radio,
} from "lucide-react";
import type { ProgressEvent } from "../api/types";

interface NodeDef {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
}

const NODE_DEFS: Record<string, NodeDef> = {
  intake_guard: {
    label: "Intake Guard",
    icon: Shield,
    description: "Validating civic relevance, MIME integrity, and safety filters",
  },
  perceive: {
    label: "Multimodal Perception",
    icon: Eye,
    description: "Extracting damage geometry, hazard indicators, and audio transcription",
  },
  geo_resolver: {
    label: "Geo & POI Resolver",
    icon: Compass,
    description: "GPS / EXIF fallback, Nominatim reverse geocode, Overpass school/hospital POIs",
  },
  deduplicator: {
    label: "Geo-Spatial Deduplicator",
    icon: GitMerge,
    description: "500m radius query and vector embedding cosine similarity clustering",
  },
  severity_scorer: {
    label: "Severity Scorer",
    icon: Scale,
    description: "Deterministic rubric calculation from hazard type, road class, and POI proximity",
  },
  authority_router: {
    label: "Jurisdiction & Rule-Based Router",
    icon: Building2,
    description: "Deterministic rule engine matching department jurisdictions and statutory charters",
  },
  critic: {
    label: "Verification Critic",
    icon: CheckCircle2,
    description: "Schema validation, confidence threshold audit, and evidence verification",
  },
  dispatcher: {
    label: "Legal Ticket Dispatcher",
    icon: FileCheck2,
    description: "Generating formal complaint, calculating SLA deadline, logging audit trace",
  },
};

const NODE_ORDER = [
  "intake_guard",
  "perceive",
  "geo_resolver",
  "deduplicator",
  "severity_scorer",
  "authority_router",
  "critic",
  "dispatcher",
];

interface Props {
  events: ProgressEvent[];
  sseStatus: "connecting" | "open" | "closed" | "error";
  onViewIssue?: (issueId: string) => void;
  onRevise?: (reason?: string) => void;
}

export default function ProgressTracker({ events, sseStatus, onViewIssue, onRevise }: Props) {
  // Map latest event per node
  const latestByNode = new Map<string, ProgressEvent>();
  for (const event of events) {
    latestByNode.set(event.node, event);
  }

  // Detect completion
  const terminalEvent = events.find(
    (e) =>
      (e.node === "dispatcher" && e.status === "done") ||
      (e.node === "__terminal__" && e.status === "complete")
  );
  const completedIssueId = terminalEvent?.data?.issue_id as string | undefined;

  // Detect rejection or failure
  const rejectionEvent = events.find(
    (e) =>
      e.status === "error" ||
      (e.node === "__terminal__" && e.data?.final_status === "rejected") ||
      (e.node === "intake_guard" && e.message?.toLowerCase().includes("unsupported"))
  );

  return (
    <div className="w-full space-y-6">
      {/* Header status bar */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-800">
        <div>
          <h2 className="text-xl sm:text-2xl font-black text-slate-900 dark:text-white tracking-tight">
            LangGraph Execution Stream
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            8-node autonomous civic decision graph
          </p>
        </div>

        <div className="flex items-center gap-2">
          {sseStatus === "open" && (
            <span className="flex items-center gap-1.5 text-xs font-bold px-3 py-1 rounded-full bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800/80 shadow-xs">
              <Radio className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400 animate-pulse" />
              <span>Live SSE Stream</span>
            </span>
          )}
          {rejectionEvent && sseStatus === "closed" && (
            <span className="text-xs font-bold px-3 py-1 rounded-full bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800/80">
              Needs Revision
            </span>
          )}
          {!rejectionEvent && sseStatus === "closed" && (
            <span className="text-xs font-bold px-3 py-1 rounded-full bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/80">
              Completed
            </span>
          )}
          {sseStatus === "connecting" && (
            <span className="text-xs font-bold px-3 py-1 rounded-full bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200">
              Connecting…
            </span>
          )}
        </div>
      </div>

      {/* Progress Timeline */}
      <div className="relative border-l-2 border-slate-200 dark:border-slate-800 ml-4 space-y-5 pl-6 sm:pl-8 my-4">
        {NODE_ORDER.map((node) => {
          const event = latestByNode.get(node);
          const def = NODE_DEFS[node];
          const Icon = def.icon;

          const isRunning = event?.status === "running";
          const isDone = event?.status === "done" || event?.status === "complete";
          const isError = event?.status === "error";

          return (
            <div key={node} className="relative group">
              {/* Timeline Node Badge Icon */}
              <div
                className={`absolute -left-[35px] sm:-left-[43px] flex items-center justify-center w-8 sm:w-9 h-8 sm:h-9 rounded-full border-2 text-xs transition-all ${
                  isRunning
                    ? "bg-blue-600 border-blue-300 text-white shadow-lg shadow-blue-500/30 scale-110 animate-pulse-glow"
                    : isDone
                    ? "bg-emerald-500 border-emerald-300 text-white shadow-sm"
                    : isError
                    ? "bg-rose-500 border-rose-300 text-white"
                    : "bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700 text-slate-400"
                }`}
              >
                {isRunning ? (
                  <Loader2 className="w-4 h-4 animate-spin text-white" />
                ) : isDone ? (
                  <CheckCircle2 className="w-4 h-4 text-white" />
                ) : isError ? (
                  <AlertTriangle className="w-4 h-4 text-white" />
                ) : (
                  <Icon className="w-4 h-4" />
                )}
              </div>

              {/* Node Card Container */}
              <div
                className={`p-4 rounded-2xl border transition-all ${
                  isRunning
                    ? "bg-blue-50/70 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800/80 shadow-md ring-1 ring-blue-400/30"
                    : isDone
                    ? "bg-white dark:bg-slate-900 border-slate-200/90 dark:border-slate-800 shadow-xs"
                    : "bg-slate-50/40 dark:bg-slate-900/40 border-slate-100 dark:border-slate-800/50 opacity-60"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <h3 className="font-black text-sm text-slate-900 dark:text-white">
                      {def.label}
                    </h3>
                    {isRunning && (
                      <span className="text-[10px] font-extrabold uppercase tracking-wider bg-blue-600 text-white px-2 py-0.5 rounded-full animate-pulse">
                        Executing
                      </span>
                    )}
                    {(isError || event?.message?.toLowerCase().includes("unsupported") || event?.message?.toLowerCase().includes("rejected")) && (
                      <span className="text-[10px] font-bold text-rose-700 dark:text-rose-300 bg-rose-50 dark:bg-rose-950/60 px-2 py-0.5 rounded-full border border-rose-200 dark:border-rose-800">
                        {event?.message?.toLowerCase().includes("rejected") || event?.message?.toLowerCase().includes("unsupported") ? "Rejected" : "Failed"}
                      </span>
                    )}
                    {isDone && !isError && !event?.message?.toLowerCase().includes("unsupported") && !event?.message?.toLowerCase().includes("rejected") && (
                      <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/60 px-2 py-0.5 rounded-full border border-emerald-200/60 dark:border-emerald-800/60">
                        Resolved
                      </span>
                    )}
                  </div>
                </div>

                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  {event?.message || def.description}
                </p>

                {/* Telemetry metadata tags */}
                {event?.data && Object.keys(event.data).length > 0 && (
                  <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-slate-800 grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] font-mono">
                    {Object.entries(event.data).map(([k, v]) => (
                      <div
                        key={k}
                        className="bg-slate-100/80 dark:bg-slate-800/80 px-2 py-1 rounded-lg truncate text-slate-700 dark:text-slate-300 border border-slate-200/50 dark:border-slate-700/50"
                      >
                        <span className="text-slate-400 font-sans mr-1">{k}:</span>
                        <span className="font-bold">
                          {typeof v === "object" ? JSON.stringify(v) : String(v)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Done Banner & Direct Action */}
      {completedIssueId && (
        <div className="p-5 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-md animate-fade-in">
          <div>
            <h3 className="text-sm font-black text-emerald-900 dark:text-emerald-200 flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
              <span>Grievance Triaged &amp; Dispatched!</span>
            </h3>
            <p className="text-xs text-emerald-700 dark:text-emerald-400 mt-0.5">
              Redirecting to public grievance file and statutory audit trace…
            </p>
          </div>
          {onViewIssue && (
            <button
              type="button"
              onClick={() => onViewIssue(completedIssueId)}
              className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow-sm flex items-center gap-1.5 transition cursor-pointer self-start sm:self-auto shrink-0"
            >
              <span>View Issue File</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      )}

      {/* Rejection / Correction Banner */}
      {!completedIssueId && rejectionEvent && (
        <div className="p-5 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-md animate-fade-in">
          <div>
            <h3 className="text-sm font-black text-rose-900 dark:text-rose-200 flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4 text-rose-600 dark:text-rose-400" />
              <span>Submission Needs Correction</span>
            </h3>
            <p className="text-xs text-rose-700 dark:text-rose-400 mt-0.5">
              {rejectionEvent.message || "This report could not be validated. Please provide a clear image, audio note, or description."}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              if (onRevise) {
                onRevise(rejectionEvent.message);
              } else {
                window.location.href = "/";
              }
            }}
            className="bg-rose-600 hover:bg-rose-700 text-white text-xs font-black px-4 py-2.5 rounded-xl shadow-md hover:shadow-lg flex items-center gap-1.5 transition cursor-pointer self-start sm:self-auto shrink-0"
          >
            <span>Update &amp; Resubmit</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * frontend/src/pages/IssuePage.tsx
 * =================================
 * High-detail issue triage file:
 * - Deterministic Priority Score breakdown (SeverityGauge)
 * - Citizen Community Confirmation button (+1 report cluster)
 * - Grounded statutory citations card (Pan-India acts & municipal codes)
 * - Official formal complaint text with 1-click clipboard copy
 * - Complete 8-node LangGraph execution trace with execution timings
 */

import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  ArrowLeft,
  ThumbsUp,
  Copy,
  Check,
  FileText,
  Clock,
  Layers,
  MapPin,
  Scale,
  Calendar,
} from "lucide-react";
import { getIssue, confirmIssue } from "../api/client";
import type { IssueOut } from "../api/types";
import SeverityGauge from "../components/SeverityGauge";
import TicketBadge from "../components/TicketBadge";

export default function IssuePage() {
  const { issueId } = useParams<{ issueId: string }>();
  const [issue, setIssue] = useState<IssueOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);
  const [confirmedSuccess, setConfirmedSuccess] = useState(false);
  const [copiedComplaint, setCopiedComplaint] = useState(false);

  const fetchIssueData = () => {
    if (!issueId) return;
    getIssue(issueId)
      .then(setIssue)
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    fetchIssueData();
  }, [issueId]);

  const handleConfirm = async () => {
    if (!issueId) return;
    setIsConfirming(true);
    try {
      await confirmIssue(issueId, `citizen-confirm-${Date.now()}`, "Confirmed directly by community citizen");
      setConfirmedSuccess(true);
      fetchIssueData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to confirm issue");
    } finally {
      setIsConfirming(false);
    }
  };

  const handleCopyComplaint = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedComplaint(true);
    setTimeout(() => setCopiedComplaint(false), 2000);
  };

  if (error) {
    return (
      <div className="py-16 px-4 flex flex-col items-center justify-center">
        <div className="bg-white dark:bg-slate-900 p-8 rounded-3xl border border-rose-200 dark:border-rose-900 text-center space-y-4 max-w-md shadow-xl">
          <div className="w-12 h-12 rounded-full bg-rose-100 dark:bg-rose-950/60 text-rose-600 flex items-center justify-center mx-auto text-xl font-bold">
            !
          </div>
          <h2 className="text-xl font-black text-slate-900 dark:text-white">Issue File Not Found</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">{error}</p>
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-1.5 bg-blue-600 text-white text-xs font-bold px-5 py-2.5 rounded-xl shadow-md"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Return to Public Dashboard</span>
          </Link>
        </div>
      </div>
    );
  }

  if (!issue) {
    return (
      <div className="py-24 flex items-center justify-center">
        <div className="flex items-center gap-3 text-slate-600 dark:text-slate-400 font-bold text-sm bg-white dark:bg-slate-900 px-6 py-4 rounded-2xl shadow-lg border border-slate-200 dark:border-slate-800">
          <span className="w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
          <span>Retrieving Immutable Audit Records…</span>
        </div>
      </div>
    );
  }

  // Extract dispatcher output for complaint text & ticket
  const dispatcherStep = issue.trace?.find((t) => t.node === "dispatcher");
  const displayScore = Math.round(
    issue.score_breakdown?.total ??
    (issue.priority_score <= 1.0 && issue.priority_score > 0
      ? issue.priority_score * 100
      : issue.priority_score)
  );
  const complaintText =
    (dispatcherStep?.output_summary?.complaint_text as string) ||
    `FORMAL CIVIC GRIEVANCE NOTICE (UNDER MUNICIPAL CHARTER STANDARDS)\n\nReference Issue ID: ${issue._id}\nCategory: ${issue.category.toUpperCase()}\nLocation: ${issue.address || "Urban Zone"}\nPriority Score: ${displayScore}/100 (${issue.severity_tier.toUpperCase()})\n\nIncident has been formally classified under Municipal Corporation Standards. Expedited remediation required within designated statutory SLA hours.`;

  // Extract router output — support both trace format and rule-based fields
  const routerStep = issue.trace?.find((t) => t.node === "authority_router");
  const authorityData = routerStep?.output_summary;

  // Department info — prefer new rule-based fields on issue, fall back to trace
  const departmentName =
    issue.department_name ||
    (authorityData?.primary_authority as string) ||
    "Municipal Corporation";
  const departmentId = issue.department_id || "";
  const routingRuleId = issue.routing_rule_id || (authorityData?.rule_id as string) || null;
  const routingConfidence = issue.routing_confidence ?? (authorityData?.confidence as number) ?? null;
  const routingJurisdiction = issue.routing_jurisdiction || (authorityData?.jurisdiction as string) || null;
  const routingSubtype = issue.routing_subtype || null;
  const routingAssetType = issue.routing_asset_type || null;
  const requiresHumanReview = issue.routing_requires_human_review || false;

  return (
    <div className="py-8 sm:py-12 px-4 sm:px-6 lg:px-8 max-w-5xl mx-auto space-y-6 animate-fade-in">
      {/* Navigation Breadcrumb */}
      <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
        <Link
          to="/dashboard"
          className="hover:text-blue-600 dark:hover:text-blue-400 flex items-center gap-1.5 font-bold transition"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Public Dashboard</span>
        </Link>
        <span className="font-mono bg-slate-100 dark:bg-slate-800 px-2.5 py-1 rounded-lg">
          Record #{issue._id.slice(-8)}
        </span>
      </div>

      {/* Main Issue Header Card */}
      <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200/90 dark:border-slate-800 p-6 sm:p-8 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs uppercase font-black tracking-wider px-3 py-1 rounded-full bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-900">
                {issue.category.replace("_", " ")}
              </span>
              {issue.status === "resolved" ? (
                <span className="text-xs uppercase font-black tracking-wider px-3 py-1 rounded-full bg-emerald-100 dark:bg-emerald-950/80 text-emerald-800 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800 flex items-center gap-1.5 shadow-xs">
                  <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                  <span>Resolved</span>
                </span>
              ) : issue.status === "in_progress" ? (
                <span className="text-xs uppercase font-black tracking-wider px-3 py-1 rounded-full bg-blue-100 dark:bg-blue-950/80 text-blue-800 dark:text-blue-300 border border-blue-300 dark:border-blue-800 flex items-center gap-1.5 shadow-xs">
                  <Clock className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
                  <span>In Progress</span>
                </span>
              ) : null}
              <span className="text-xs text-slate-400 flex items-center gap-1">
                <Calendar className="w-3.5 h-3.5" />
                <span>{new Date(issue.created_at).toLocaleDateString()}</span>
              </span>
            </div>

            <h1 className="text-2xl sm:text-3xl font-black text-slate-900 dark:text-white leading-tight">
              {issue.address || "Urban Civic Location"}
            </h1>

            {issue.ward && (
              <p className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1.5 font-mono">
                <MapPin className="w-3.5 h-3.5 text-blue-500" />
                <span>Ward: {issue.ward}</span>
                <span>•</span>
                <span>
                  {issue.location.coordinates[1].toFixed(4)}°N, {issue.location.coordinates[0].toFixed(4)}°E
                </span>
              </p>
            )}
          </div>

          {/* Citizen Community Confirmation Button */}
          <div className="flex flex-col sm:items-end gap-2">
            <button
              type="button"
              onClick={handleConfirm}
              disabled={isConfirming || confirmedSuccess}
              className={`px-5 py-3 rounded-2xl text-xs font-black transition-all flex items-center gap-2 shadow-sm cursor-pointer ${confirmedSuccess
                ? "bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800"
                : "bg-blue-600 hover:bg-blue-700 text-white shadow-blue-500/20"
                }`}
            >
              <ThumbsUp className="w-4 h-4" />
              <span>
                {confirmedSuccess
                  ? "Confirmed by You (+1 Upvote)"
                  : `Confirm This Grievance (${issue.report_count} Reports)`}
              </span>
            </button>
            <span className="text-[11px] text-slate-400 dark:text-slate-500">
              Geo-clustered across {issue.report_count} duplicate citizen reports
            </span>
          </div>
        </div>
      </div>

      {/* Grid: Severity Gauge & Authority Routing */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Priority Score Breakdown */}
        <SeverityGauge
          score={issue.priority_score}
          tier={issue.severity_tier}
          breakdown={issue.score_breakdown}
        />

        {/* Ticket & Department Routing */}
        <div className="space-y-4">
          <TicketBadge
            authorityName={departmentName}
            tier={`Tier ${(authorityData?.tier as number) ?? 1}: ${departmentName.split("(")[0].trim()}`}
            slaDeadline={
              issue.score_breakdown
                ? new Date(
                  new Date(issue.created_at).getTime() +
                  (issue.severity_tier === "critical"
                    ? 4
                    : issue.severity_tier === "high"
                      ? 24
                      : 72) *
                  3600 *
                  1000
                ).toISOString()
                : undefined
            }
            status={issue.status}
            isFlagged={issue.status === "escalated"}
          />

          {/* Rule-Based Routing Provenance */}
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/90 dark:border-slate-800 p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-extrabold uppercase tracking-wider text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                <Scale className="w-4 h-4 text-indigo-600" />
                <span>Routing Engine Provenance</span>
              </span>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md border ${
                requiresHumanReview
                  ? "text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/60 border-amber-200 dark:border-amber-900"
                  : "text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/60 border-indigo-200 dark:border-indigo-900"
              }`}>
                {requiresHumanReview ? "Human Review" : "Rule-Based"}
              </span>
            </div>

            <div className="space-y-2">
              {routingRuleId && (
                <div className="p-3 bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800 rounded-xl text-xs space-y-1">
                  <span className="font-black text-slate-900 dark:text-white block">
                    Matched Rule: <span className="font-mono text-indigo-600 dark:text-indigo-400">{routingRuleId}</span>
                  </span>
                  {routingSubtype && (
                    <span className="text-[11px] text-slate-500 dark:text-slate-400 block">
                      Subtype: <strong>{routingSubtype}</strong>
                      {routingAssetType && <> · Asset: <strong>{routingAssetType}</strong></>}
                    </span>
                  )}
                  {routingJurisdiction && (
                    <span className="text-[11px] text-slate-500 dark:text-slate-400 block">
                      Jurisdiction: {routingJurisdiction}
                    </span>
                  )}
                  {routingConfidence !== null && (
                    <span className="text-[11px] text-slate-500 dark:text-slate-400 block">
                      Confidence: <strong>{(routingConfidence * 100).toFixed(0)}%</strong>
                    </span>
                  )}
                </div>
              )}
              {issue.source_document_ids && issue.source_document_ids.length > 0 && (
                <div className="p-3 bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800 rounded-xl text-xs space-y-1">
                  <span className="font-black text-slate-900 dark:text-white block">
                    Statutory Sources
                  </span>
                  {issue.source_document_ids.map((docId) => (
                    <span key={docId} className="text-[11px] text-indigo-600 dark:text-indigo-400 font-mono block">
                      • {docId}
                    </span>
                  ))}
                </div>
              )}
              {!routingRuleId && !issue.source_document_ids?.length && (
                <div className="p-3 bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800 rounded-xl text-xs">
                  <span className="text-slate-500 dark:text-slate-400 block">
                    Routing provenance available after pipeline completion.
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Formal Complaint Letter Notice */}
      <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200/90 dark:border-slate-800 p-6 sm:p-8 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base sm:text-lg font-black text-slate-900 dark:text-white flex items-center gap-2">
              <FileText className="w-5 h-5 text-blue-600" />
              <span>Official Generated Complaint Notice</span>
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Ready for immediate submission to municipal grievance portals or RTI grievance filing
            </p>
          </div>
          <button
            type="button"
            onClick={() => handleCopyComplaint(complaintText)}
            className="px-3.5 py-2 rounded-xl border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-xs font-bold text-slate-700 dark:text-slate-200 transition flex items-center gap-1.5 cursor-pointer shadow-xs"
          >
            {copiedComplaint ? (
              <>
                <Check className="w-4 h-4 text-emerald-600" />
                <span>Copied to Clipboard!</span>
              </>
            ) : (
              <>
                <Copy className="w-4 h-4" />
                <span>Copy Notice</span>
              </>
            )}
          </button>
        </div>

        <div className="p-5 bg-slate-950 dark:bg-black rounded-2xl font-mono text-xs text-slate-200 whitespace-pre-wrap leading-relaxed shadow-inner overflow-x-auto max-h-72 border border-slate-800">
          {complaintText}
        </div>
      </div>

      {/* 8-Node LangGraph Audit Trace */}
      {issue.trace && issue.trace.length > 0 && (
        <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200/90 dark:border-slate-800 p-6 sm:p-8 shadow-sm space-y-5">
          <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-4">
            <div>
              <h3 className="text-base sm:text-lg font-black text-slate-900 dark:text-white flex items-center gap-2">
                <Layers className="w-5 h-5 text-indigo-600" />
                <span>Autonomous Agent Pipeline Trace</span>
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                Immutable audit trail of all LangGraph decisions and tool invocations
              </p>
            </div>
            <span className="text-xs font-bold text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 px-3 py-1 rounded-full">
              {issue.trace.length} nodes logged
            </span>
          </div>

          <div className="space-y-3">
            {issue.trace.map((step, idx) => (
              <div
                key={idx}
                className="p-4 bg-slate-50 dark:bg-slate-800/50 rounded-2xl border border-slate-200/70 dark:border-slate-800 text-xs space-y-2"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-6 h-6 rounded-full bg-blue-100 dark:bg-blue-950/80 text-blue-700 dark:text-blue-300 flex items-center justify-center font-bold text-xs">
                      {idx + 1}
                    </span>
                    <span className="font-mono font-black text-slate-900 dark:text-white text-sm">
                      {step.node}
                    </span>
                  </div>
                  <span className="text-[11px] font-bold text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/60 px-2.5 py-0.5 rounded-full border border-emerald-200/60 dark:border-emerald-800/60">
                    {step.status}
                  </span>
                </div>

                {step.output_summary && Object.keys(step.output_summary).length > 0 && (
                  <div className="bg-white dark:bg-slate-900 p-3.5 rounded-xl border border-slate-200/80 dark:border-slate-800 text-[11px] space-y-2">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 font-mono">
                      {Object.entries(step.output_summary).map(([k, v]) => (
                        <div
                          key={k}
                          className="bg-slate-50 dark:bg-slate-800/60 p-2 rounded-lg border border-slate-100 dark:border-slate-800/80"
                        >
                          <span className="text-slate-400 font-sans block text-[10px] uppercase font-bold">
                            {k.replace(/_/g, " ")}
                          </span>
                          <span className="text-slate-800 dark:text-slate-200 font-bold break-words">
                            {typeof v === "object" && v !== null
                              ? JSON.stringify(v)
                              : String(v).replace(/IssueCategory\./g, "")}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

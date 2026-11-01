/**
 * frontend/src/pages/ProgressPage.tsx
 * =====================================
 * Live progress page shown after report submission.
 * Connects to SSE stream and renders ProgressTracker.
 * Automatically redirects to the triaged issue page upon completion.
 */

import React, { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertCircle } from "lucide-react";
import ProgressTracker from "../components/ProgressTracker";
import { useSSE } from "../hooks/useSSE";
import { clearDraft } from "../utils/draftStore";

export default function ProgressPage() {
  const { reportId } = useParams<{ reportId: string }>();
  const navigate = useNavigate();
  const { events, status } = useSSE(reportId ? `/reports/${reportId}/stream` : null);

  // Auto-redirect to issue page when pipeline completes
  useEffect(() => {
    const doneEvent = events.find(
      (e) =>
        (e.node === "dispatcher" && e.status === "done") ||
        (e.node === "__terminal__" && e.status === "complete")
    );
    if (doneEvent?.data?.issue_id) {
      const issueId = doneEvent.data.issue_id as string;
      clearDraft();
      const timer = setTimeout(() => {
        navigate(`/issues/${issueId}`);
      }, 1600);
      return () => clearTimeout(timer);
    }
  }, [events, navigate]);

  const handleRevise = (reason?: string) => {
    navigate("/", { state: { fromRejection: true, reason } });
  };

  return (
    <div className="py-8 sm:py-12 px-4 sm:px-6 lg:px-8 max-w-3xl mx-auto flex justify-center">
      <div className="w-full bg-white dark:bg-slate-900 rounded-3xl shadow-xl border border-slate-200/90 dark:border-slate-800 p-6 sm:p-8">
        <ProgressTracker
          events={events}
          sseStatus={status}
          onViewIssue={(id) => navigate(`/issues/${id}`)}
          onRevise={handleRevise}
        />
        {status === "error" && (
          <div className="mt-6 p-4 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 rounded-2xl flex items-center gap-2 text-center text-xs font-bold text-rose-700 dark:text-rose-300">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
            <span>SSE stream disconnected. Reconnecting automatically to event bus…</span>
          </div>
        )}
      </div>
    </div>
  );
}

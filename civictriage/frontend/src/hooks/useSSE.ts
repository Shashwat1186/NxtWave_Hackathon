/**
 * frontend/src/hooks/useSSE.ts
 * ============================
 * React hook for consuming Server-Sent Events.
 *
 * Features:
 * - Automatic reconnect with Last-Event-ID
 * - Typed ProgressEvent parsing
 * - Returns accumulated events array + connection status
 *
 * Usage:
 *   const { events, status } = useSSE(`/reports/${reportId}/stream`);
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { ProgressEvent } from "../api/types";

type SSEStatus = "connecting" | "open" | "closed" | "error";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY_MS = 2000;

export function useSSE(path: string | null) {
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [status, setStatus] = useState<SSEStatus>("closed");
  const esRef = useRef<EventSource | null>(null);
  const reconnectCount = useRef(0);
  const lastEventId = useRef<string | undefined>(undefined);

  const connect = useCallback(() => {
    if (!path) return;

    setStatus("connecting");
    const url = lastEventId.current
      ? `${BASE_URL}${path}?lastEventId=${lastEventId.current}`
      : `${BASE_URL}${path}`;

    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => {
      setStatus("open");
      reconnectCount.current = 0;
    };

    es.onmessage = (e) => {
      lastEventId.current = e.lastEventId || undefined;
      try {
        const event: ProgressEvent = JSON.parse(e.data);
        setEvents((prev) => [...prev, event]);

        // Close stream when pipeline signals completion
        if (event.node === "__done__" || event.status === "complete") {
          es.close();
          setStatus("closed");
        }
      } catch {
        // Ignore non-JSON heartbeat lines
      }
    };

    es.onerror = () => {
      es.close();
      setStatus("error");
      if (reconnectCount.current < MAX_RECONNECT_ATTEMPTS) {
        reconnectCount.current += 1;
        setTimeout(connect, RECONNECT_DELAY_MS * reconnectCount.current);
      }
    };
  }, [path]);

  useEffect(() => {
    if (!path) return;
    setEvents([]);
    reconnectCount.current = 0;
    connect();
    return () => {
      esRef.current?.close();
    };
  }, [path, connect]);

  return { events, status };
}


/**
 * frontend/src/map/IssueMap.tsx
 * ==============================
 * Interactive Leaflet GIS map with:
 * - Color-coded severity pins (Critical: Red, High: Orange, Medium: Amber, Low: Emerald)
 * - Category, Severity, and Status interactive filter controls
 * - Custom card popups with cluster count, score, and drilldown link
 * - Dark mode compatible container
 */

import React, { useEffect, useState, useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { RefreshCw, Filter, ArrowRight } from "lucide-react";
import { listIssues } from "../api/client";
import type { IssueCategory, IssueOut, IssueStatus, SeverityTier } from "../api/types";
import { Link } from "react-router-dom";

const SEVERITY_COLORS: Record<SeverityTier, string> = {
  critical: "#dc2626", // Red-600
  high: "#ea580c",     // Orange-600
  medium: "#d97706",   // Amber-600
  low: "#059669",      // Emerald-600
};

const DEFAULT_CENTER: [number, number] = [17.4065, 78.435]; // Hyderabad Center
const DEFAULT_ZOOM = 12;

interface IssueMapProps {
  initialCategory?: IssueCategory;
  initialStatus?: IssueStatus;
  height?: string | number;
}

function MapUpdater({ issues }: { issues: IssueOut[] }) {
  const map = useMap();
  useEffect(() => {
    if (issues.length > 0) {
      const validCoords = issues
        .map((i) => i.location?.coordinates)
        .filter((c) => c && c.length === 2 && c[0] !== 0 && c[1] !== 0);

      if (validCoords.length > 0) {
        const first = validCoords[0];
        map.setView([first[1], first[0]], DEFAULT_ZOOM);
      }
    }
  }, [issues, map]);
  return null;
}

export default function IssueMap({
  initialCategory,
  initialStatus,
  height = "100%",
}: IssueMapProps) {
  const [issues, setIssues] = useState<IssueOut[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState<string>(initialCategory || "all");
  const [selectedSeverity, setSelectedSeverity] = useState<string>("all");
  const [selectedStatus, setSelectedStatus] = useState<string>(initialStatus || "all");

  const fetchIssues = () => {
    setIsLoading(true);
    listIssues({ page_size: 100 })
      .then((res) => setIssues(res.items || []))
      .catch((err) => console.error("Failed to load map issues:", err))
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    fetchIssues();
  }, []);

  const filteredIssues = useMemo(() => {
    return issues.filter((item) => {
      if (selectedCategory !== "all" && item.category !== selectedCategory) return false;
      if (selectedSeverity !== "all" && item.severity_tier !== selectedSeverity) return false;
      if (selectedStatus !== "all" && item.status !== selectedStatus) return false;
      return true;
    });
  }, [issues, selectedCategory, selectedSeverity, selectedStatus]);

  return (
    <div className="relative w-full h-full flex flex-col rounded-3xl overflow-hidden border border-slate-200/90 dark:border-slate-800 shadow-md bg-white dark:bg-slate-900">
      {/* Map Filter Bar */}
      <div className="p-3.5 bg-white dark:bg-slate-900 border-b border-slate-200/80 dark:border-slate-800 flex flex-wrap items-center justify-between gap-2.5 z-10">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5 text-xs font-bold text-slate-500 dark:text-slate-400 mr-1">
            <Filter className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Filters:</span>
          </div>

          {/* Category Filter */}
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="text-xs font-bold border border-slate-300 dark:border-slate-700 rounded-xl px-3 py-1.5 bg-slate-50 dark:bg-slate-800 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">All Categories</option>
            <option value="road_damage">Road Damage</option>
            <option value="water_leak">Water Leak</option>
            <option value="sewage">Sewage Overflow</option>
            <option value="garbage">Garbage / Sanitation</option>
            <option value="streetlight">Streetlight</option>
            <option value="pollution">Pollution</option>
          </select>

          {/* Severity Filter */}
          <select
            value={selectedSeverity}
            onChange={(e) => setSelectedSeverity(e.target.value)}
            className="text-xs font-bold border border-slate-300 dark:border-slate-700 rounded-xl px-3 py-1.5 bg-slate-50 dark:bg-slate-800 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">All Severities</option>
            <option value="critical">Critical (80+)</option>
            <option value="high">High (60-79)</option>
            <option value="medium">Medium (40-59)</option>
            <option value="low">Low (&lt;40)</option>
          </select>

          {/* Status Filter */}
          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            className="text-xs font-bold border border-slate-300 dark:border-slate-700 rounded-xl px-3 py-1.5 bg-slate-50 dark:bg-slate-800 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">All Statuses</option>
            <option value="open">Open</option>
            <option value="assigned">Assigned</option>
            <option value="in_progress">In Progress</option>
            <option value="resolved">Resolved</option>
          </select>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <span className="font-bold text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 px-2.5 py-1 rounded-lg">
            {filteredIssues.length} Geocoded Points
          </span>
          <button
            type="button"
            onClick={fetchIssues}
            disabled={isLoading}
            className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 transition cursor-pointer"
            title="Refresh Map Points"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-blue-600" : ""}`} />
          </button>
        </div>
      </div>

      {/* Map View — isolation:isolate prevents z-index leak above sticky nav */}
      <div className="relative flex-1 w-full" style={{ minHeight: height, isolation: "isolate" }}>
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/70 dark:bg-slate-900/70 z-20 backdrop-blur-2xs">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 px-4 py-2 rounded-2xl shadow-lg border border-slate-200 dark:border-slate-700">
              <span className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
              <span>Updating GIS Spatial Index…</span>
            </div>
          </div>
        )}

        <MapContainer
          center={DEFAULT_CENTER}
          zoom={DEFAULT_ZOOM}
          className="w-full h-full"
          scrollWheelZoom={true}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <MapUpdater issues={filteredIssues} />

          {filteredIssues.map((issue) => {
            const coords = issue.location?.coordinates;
            if (!coords || coords.length < 2) return null;
            const [lng, lat] = coords;
            if (!lat || !lng) return null;

            const color = SEVERITY_COLORS[issue.severity_tier] ?? "#64748b";
            const radius = Math.min(22, 9 + (issue.report_count || 1) * 2.5);

            return (
              <CircleMarker
                key={issue._id}
                center={[lat, lng]}
                radius={radius}
                pathOptions={{
                  color: color,
                  fillColor: color,
                  fillOpacity: 0.8,
                  weight: 2.5,
                }}
              >
                <Popup>
                  <div className="p-1 max-w-[220px] space-y-2 font-sans">
                    <div className="flex items-center justify-between gap-1 flex-wrap">
                      <span className="text-[10px] font-black uppercase tracking-wider text-slate-500">
                        {issue.category.replace("_", " ")}
                      </span>
                      <div className="flex items-center gap-1">
                        {issue.status === "resolved" && (
                          <span className="text-[9px] font-black px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300">
                            ✓ Resolved
                          </span>
                        )}
                        {issue.status === "in_progress" && (
                          <span className="text-[9px] font-black px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-300">
                            In Progress
                          </span>
                        )}
                        <span
                          className="text-[10px] font-black px-2 py-0.5 rounded-full uppercase"
                          style={{
                            backgroundColor: `${color}20`,
                            color: color,
                          }}
                        >
                          {issue.severity_tier}
                        </span>
                      </div>
                    </div>

                    <h4 className="text-xs font-black text-slate-900 leading-snug">
                      {issue.address || "Urban Civic Location"}
                    </h4>

                    <div className="flex items-center justify-between text-[11px] text-slate-600 pt-1.5 border-t border-slate-100">
                      <span>{issue.report_count} citizen report{issue.report_count !== 1 ? "s" : ""}</span>
                      <span className="font-mono font-bold">
                        Score:{" "}
                        {Math.round(
                          issue.priority_score <= 1.0 && issue.priority_score > 0
                            ? issue.priority_score * 100
                            : issue.priority_score
                        )}
                      </span>
                    </div>

                    <Link
                      to={`/issues/${issue._id}`}
                      className="flex items-center justify-center gap-1 w-full text-center mt-2 bg-blue-600 hover:bg-blue-700 text-white text-[11px] font-bold py-1.5 px-2 rounded-xl transition-colors no-underline shadow-xs"
                    >
                      <span>Inspect Triage File</span>
                      <ArrowRight className="w-3 h-3" />
                    </Link>
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}
        </MapContainer>
      </div>
    </div>
  );
}

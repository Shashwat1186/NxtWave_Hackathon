/**
 * frontend/src/utils/draftStore.ts
 * =================================
 * In-memory and session-persistent report draft store.
 * Preserves user-entered description, attached image/audio File, and GPS coordinates
 * so that if an issue is rejected or fails validation, the user can revise and resubmit
 * without losing any input.
 */

export interface ReportDraft {
  description: string;
  file: File | null;
  gpsLat: number | null;
  gpsLng: number | null;
  locationName: string;
}

let inMemoryDraft: ReportDraft | null = null;

const STORAGE_KEY = "civictriage_last_draft";

export function saveDraft(draft: ReportDraft): void {
  inMemoryDraft = draft;
  try {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        description: draft.description,
        gpsLat: draft.gpsLat,
        gpsLng: draft.gpsLng,
        locationName: draft.locationName,
      })
    );
  } catch (err) {
    console.warn("Could not save draft to sessionStorage", err);
  }
}

export function getDraft(): ReportDraft | null {
  if (inMemoryDraft) {
    return inMemoryDraft;
  }
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        description: parsed.description || "",
        file: null,
        gpsLat: parsed.gpsLat ?? null,
        gpsLng: parsed.gpsLng ?? null,
        locationName: parsed.locationName || "",
      };
    }
  } catch (err) {
    console.warn("Could not retrieve draft from sessionStorage", err);
  }
  return null;
}

export function clearDraft(): void {
  inMemoryDraft = null;
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch (err) {
    console.warn("Could not clear draft from sessionStorage", err);
  }
}


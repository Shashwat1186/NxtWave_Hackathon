/**
 * frontend/src/pages/SubmitPage.tsx
 * ==================================
 * High-performance, mobile-first report submission studio.
 *
 * Capabilities:
 * - Direct Live Webcam / Mobile Camera Viewfinder with instant photo capture
 * - Drag-and-Drop & File Picker for images and audio files with high-res preview
 * - Voice Note recording with MediaRecorder and animated audio visualizer
 * - Auto-GPS Geolocation + Pan-India City Quick-Picker (Delhi, Mumbai, Bengaluru, Hyderabad, etc.)
 * - 4 One-Click Demo Scenarios for instant judging demonstrations
 * - Direct submission to POST /reports -> live SSE LangGraph stream
 */

import React, { useState, useRef, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  Camera,
  UploadCloud,
  Mic,
  Square,
  MapPin,
  Sparkles,
  AlertCircle,
  ArrowRight,
  X,
  Compass,
  CheckCircle2,
  RefreshCw,
  Trash2,
  ImageIcon,
} from "lucide-react";
import { submitReport } from "../api/client";
import { getDraft, saveDraft, clearDraft } from "../utils/draftStore";

interface DemoPreset {
  title: string;
  categoryLabel: string;
  description: string;
  lat: number;
  lng: number;
  city: string;
  landmark: string;
  icon: string;
  accent: string;
  expectedSla: string;
}

const DEMO_PRESETS: DemoPreset[] = [
  {
    title: "Critical Pothole (Hospital Emergency Route)",
    categoryLabel: "Road Hazard",
    description: "Deep crater-like pothole (>18cm depth) on 4-lane arterial road causing severe vehicle swerving. Located directly adjacent to hospital emergency ambulance corridor.",
    lat: 17.4319,
    lng: 78.4087,
    city: "Hyderabad / Jubilee Hills",
    landmark: "Road No. 36, Near Apollo Hospital",
    icon: "🚧",
    accent: "border-rose-300 dark:border-rose-900 bg-rose-50/70 dark:bg-rose-950/30 text-rose-800 dark:text-rose-200",
    expectedSla: "SLA ≤ 4h (Critical)",
  },
  {
    title: "High-Pressure Water Main Rupture",
    categoryLabel: "Water Supply",
    description: "High-pressure potable water distribution pipeline ruptured underground. Water flooding 60m road stretch causing asphalt subsidence and supply shutdown to residential wards.",
    lat: 17.4485,
    lng: 78.375,
    city: "Hyderabad / Madhapur",
    landmark: "Hitec City Main Road near Cyber Towers",
    icon: "💧",
    accent: "border-blue-300 dark:border-blue-900 bg-blue-50/70 dark:bg-blue-950/30 text-blue-800 dark:text-blue-200",
    expectedSla: "SLA ≤ 12h (High)",
  },
  {
    title: "Dark Streetlight Corridor & Exposed Wire",
    categoryLabel: "Public Safety",
    description: "Series of 5 consecutive LED streetlights dead for past 4 nights. Open electrical junction box with exposed 230V live wire dangling near public pedestrian walkway.",
    lat: 17.4156,
    lng: 78.435,
    city: "Hyderabad / Banjara Hills",
    landmark: "Road No. 12 Intersection",
    icon: "💡",
    accent: "border-amber-300 dark:border-amber-900 bg-amber-50/70 dark:bg-amber-950/30 text-amber-800 dark:text-amber-200",
    expectedSla: "SLA ≤ 2h (Live Wire)",
  },
  {
    title: "Toxic Waste Burning near School Boundary",
    categoryLabel: "Biohazard & Sanitation",
    description: "Secondary municipal waste dumpster overflowing for over 72 hours. Open burning of plastic, dry leaves, and municipal garbage emitting toxic smoke within 40m of school boundary.",
    lat: 17.4399,
    lng: 78.4983,
    city: "Secunderabad",
    landmark: "Station Road near St. Ann's High School",
    icon: "🗑️",
    accent: "border-emerald-300 dark:border-emerald-900 bg-emerald-50/70 dark:bg-emerald-950/30 text-emerald-800 dark:text-emerald-200",
    expectedSla: "SLA ≤ 4h (Biohazard)",
  },
];

const POPULAR_CITIES = [
  { name: "Hyderabad", lat: 17.385, lng: 78.4867 },
  { name: "Bengaluru", lat: 12.9716, lng: 77.5946 },
  { name: "Delhi NCR", lat: 28.6139, lng: 77.209 },
  { name: "Mumbai", lat: 19.076, lng: 72.8777 },
  { name: "Chennai", lat: 13.0827, lng: 80.2707 },
  { name: "Kolkata", lat: 22.5726, lng: 88.3639 },
  { name: "Pune", lat: 18.5204, lng: 73.8567 },
];

export default function SubmitPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const locationState = location.state as { fromRejection?: boolean; reason?: string } | null;

  // Form states - Pre-filled from draft memory or sessionStorage if revising
  const draft = getDraft();

  const [description, setDescription] = useState<string>(() => draft?.description || "");
  const [file, setFile] = useState<File | null>(() => draft?.file ?? null);
  const [voiceFile, setVoiceFile] = useState<File | null>(null);
  const [filePreview, setFilePreview] = useState<string | null>(() => {
    if (draft?.file) {
      const isImg =
        draft.file.type.startsWith("image/") ||
        /\.(jpg|jpeg|png|webp|gif|bmp|svg|tiff|jfif)$/i.test(draft.file.name);
      if (isImg) {
        try {
          return URL.createObjectURL(draft.file);
        } catch (e) {
          console.error("Preview creation error:", e);
          return null;
        }
      }
    }
    return null;
  });
  const [gpsLat, setGpsLat] = useState<number | null>(() => draft?.gpsLat ?? null);
  const [gpsLng, setGpsLng] = useState<number | null>(() => draft?.gpsLng ?? null);
  const [locationName, setLocationName] = useState<string>(() => draft?.locationName || "");

  // UI state
  const [isLocating, setIsLocating] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  // Live Camera state
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [isCameraStarting, setIsCameraStarting] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [facingMode, setFacingMode] = useState<"environment" | "user">("environment");
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);

  // Audio recording state
  const [isRecording, setIsRecording] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);

  // File input refs
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const cameraInputRef = useRef<HTMLInputElement | null>(null);

  // Cleanup URLs and Media Streams on unmount
  useEffect(() => {
    return () => {
      if (filePreview) URL.revokeObjectURL(filePreview);
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      if (timerRef.current) clearInterval(timerRef.current);
      if (cameraStreamRef.current) {
        cameraStreamRef.current.getTracks().forEach((track) => track.stop());
      }
    };
  }, [filePreview, audioUrl]);

  // Robust file handler supporting images, audio, and cross-platform extensions
  const handleFileChange = (selectedFile: File | null) => {
    if (filePreview) {
      URL.revokeObjectURL(filePreview);
      setFilePreview(null);
    }

    setFile(selectedFile);
    setError(null);

    if (selectedFile) {
      const isImg =
        selectedFile.type.startsWith("image/") ||
        /\.(jpg|jpeg|png|webp|gif|bmp|svg|tiff|jfif)$/i.test(selectedFile.name);

      if (isImg) {
        try {
          const previewUrl = URL.createObjectURL(selectedFile);
          setFilePreview(previewUrl);
        } catch (e) {
          console.error("Preview creation error:", e);
        }
      } else {
        setFilePreview(null);
      }
    } else {
      setFilePreview(null);
      setAudioUrl(null);
    }
  };

  const handleVoiceFileChange = (selectedFile: File | null) => {
    setVoiceFile(selectedFile);
    setError(null);
  };

  // Drag and Drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile) {
      if (droppedFile.type.startsWith("audio/")) {
        handleVoiceFileChange(droppedFile);
      } else {
        handleFileChange(droppedFile);
      }
    }
  };

  // --- LIVE WEBCAM & CAMERA SYSTEM ---
  const startLiveCamera = async (mode: "environment" | "user" = facingMode) => {
    setCameraError(null);
    setIsCameraStarting(true);
    setIsCameraOpen(true);

    // Stop existing camera stream if already running
    if (cameraStreamRef.current) {
      cameraStreamRef.current.getTracks().forEach((t) => t.stop());
      cameraStreamRef.current = null;
    }

    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("Camera API not supported in this browser. Please use the Upload File button.");
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: mode },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });

      cameraStreamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {});
      }
      setIsCameraStarting(false);
    } catch (err: unknown) {
      setIsCameraStarting(false);
      const msg = err instanceof Error ? err.message : "Unable to access camera device";
      setCameraError(`Camera Notice: ${msg}. Click below to pick from disk or allow camera permissions in browser.`);
    }
  };

  const stopLiveCamera = () => {
    if (cameraStreamRef.current) {
      cameraStreamRef.current.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = null;
    }
    setIsCameraOpen(false);
    setIsCameraStarting(false);
    setCameraError(null);
  };

  const flipCamera = () => {
    const nextMode = facingMode === "environment" ? "user" : "environment";
    setFacingMode(nextMode);
    startLiveCamera(nextMode);
  };

  const captureLivePhoto = () => {
    if (!videoRef.current) return;
    const video = videoRef.current;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 720;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    if (facingMode === "user") {
      ctx.translate(canvas.width, 0);
      ctx.scale(-1, 1);
    }
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(
      (blob) => {
        if (blob) {
          const capturedFile = new File(
            [blob],
            `civic_photo_${Date.now()}.jpg`,
            { type: "image/jpeg" }
          );
          handleFileChange(capturedFile);
          stopLiveCamera();
        }
      },
      "image/jpeg",
      0.92
    );
  };

  // Browser Geolocation
  const handleGetLocation = () => {
    if (!navigator.geolocation) {
      setError("Geolocation is not supported by your browser.");
      return;
    }
    setIsLocating(true);
    setError(null);

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGpsLat(pos.coords.latitude);
        setGpsLng(pos.coords.longitude);
        setLocationName(
          `${pos.coords.latitude.toFixed(4)}° N, ${pos.coords.longitude.toFixed(4)}° E (GPS Lock)`
        );
        setIsLocating(false);
      },
      (err) => {
        setIsLocating(false);
        setError(`Location access: ${err.message}. Choose a city preset below.`);
        setGpsLat(17.385);
        setGpsLng(78.4867);
        setLocationName("Hyderabad Central Zone (Default)");
      },
      { timeout: 8000, enableHighAccuracy: true }
    );
  };

  // Voice recording handlers
  const startRecording = async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        const recordedFile = new File([audioBlob], `voice_grievance_${Date.now()}.webm`, {
          type: "audio/webm",
        });
        handleVoiceFileChange(recordedFile);
        const url = URL.createObjectURL(audioBlob);
        setAudioUrl(url);
        stream.getTracks().forEach((track) => track.stop());
      };

      recorder.start();
      setIsRecording(true);
      setRecordingDuration(0);
      timerRef.current = window.setInterval(() => {
        setRecordingDuration((d) => d + 1);
      }, 1000);
    } catch {
      setError("Microphone permission required for voice grievance recording.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
  };

  // Quick preset apply
  const applyPreset = (preset: DemoPreset) => {
    setDescription(preset.description);
    setGpsLat(preset.lat);
    setGpsLng(preset.lng);
    setLocationName(`${preset.landmark}, ${preset.city} (${preset.lat}, ${preset.lng})`);
    setError(null);
  };

  // Form submit
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file && !description.trim()) {
      setError("Please attach an image/video or provide a description.");
      return;
    }
    if (voiceFile && !file) {
      setError("A voice note is used only to translate the description. Please attach the matching image/video too.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    // Persist draft in memory and session storage before dispatching so it can be revised if rejected
    saveDraft({
      description,
      file,
      gpsLat,
      gpsLng,
      locationName,
    });

    try {
      const formData = new FormData();
      if (file) formData.append("file", file);
      if (voiceFile) formData.append("voice_file", voiceFile);
      if (description) formData.append("description", description);
      if (gpsLat !== null) formData.append("gps_lat", String(gpsLat));
      if (gpsLng !== null) formData.append("gps_lng", String(gpsLng));

      const response = await submitReport(formData);
      navigate(`/reports/${response.report_id}/progress`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Report submission failed.");
      setIsSubmitting(false);
    }
  };

  const handleClearDraft = () => {
    setDescription("");
    handleFileChange(null);
    handleVoiceFileChange(null);
    setGpsLat(null);
    setGpsLng(null);
    setLocationName("");
    clearDraft();
  };

  return (
    <div className="py-8 sm:py-12 px-4 sm:px-6 lg:px-8 max-w-4xl mx-auto space-y-8 animate-fade-in">
      {/* Hero Presentation Header */}
      <div className="text-center space-y-3">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-blue-100 dark:bg-blue-950/60 text-blue-800 dark:text-blue-300 border border-blue-200 dark:border-blue-800/60 shadow-xs">
          <Sparkles className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
          <span>Pan-India Autonomous Grievance Triage</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-black tracking-tight text-slate-900 dark:text-white">
          Report Civic Damage &amp; Infrastructure
        </h1>
        <p className="text-sm sm:text-base text-slate-600 dark:text-slate-400 max-w-xl mx-auto leading-relaxed">
          Submit photos, voice notes in any regional language, or text. Our 8-node LangGraph agent calculates auditable severity, matches statutory department charters, and enforces legal SLAs.
        </p>
      </div>

      {/* Revision & Resubmit Notice Banner */}
      {locationState?.fromRejection && (
        <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-800 rounded-3xl p-5 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4 animate-fade-in">
          <div className="flex items-start gap-3.5">
            <span className="p-2 rounded-2xl bg-amber-200/80 dark:bg-amber-900/60 text-amber-800 dark:text-amber-200 shrink-0 mt-0.5">
              <AlertCircle className="w-5 h-5" />
            </span>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <h4 className="text-xs font-black uppercase tracking-wider text-amber-900 dark:text-amber-200">
                  Report Restored for Revision &amp; Resubmission
                </h4>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-200/60 dark:bg-amber-900/40 text-amber-900 dark:text-amber-200">
                  Previous Details Preserved
                </span>
              </div>
              <p className="text-xs text-amber-800 dark:text-amber-300 leading-relaxed">
                {locationState.reason
                  ? `Notice: ${locationState.reason}`
                  : "Your previous submission required adjustments. Your description, attached evidence, and location coordinates have been preserved below so you can update and resubmit."}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClearDraft}
            className="text-xs font-bold px-4 py-2 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition cursor-pointer shrink-0 shadow-xs flex items-center justify-center gap-1.5"
          >
            <Trash2 className="w-3.5 h-3.5 text-slate-400" />
            <span>Start Blank</span>
          </button>
        </div>
      )}

      {/* 1-Click Judge Demo Scenarios Showcase */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200/90 dark:border-slate-800 shadow-sm space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              ⚡ 1-Click Live Test Scenarios
            </span>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800">
              Instant Autofill
            </span>
          </div>
          <span className="text-xs text-slate-400 dark:text-slate-500 hidden sm:inline">
            Click any scenario to test the full pipeline
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {DEMO_PRESETS.map((preset) => (
            <button
              key={preset.title}
              type="button"
              onClick={() => applyPreset(preset)}
              className={`p-3.5 rounded-xl border text-left transition-all hover:scale-[1.01] hover:shadow-md cursor-pointer flex flex-col justify-between ${preset.accent}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-2xl">{preset.icon}</span>
                  <div>
                    <h4 className="text-xs font-black truncate">{preset.title}</h4>
                    <p className="text-[11px] opacity-80">{preset.landmark}</p>
                  </div>
                </div>
              </div>
              <div className="mt-2.5 pt-2 border-t border-black/10 dark:border-white/10 flex items-center justify-between text-[10px] font-mono font-bold">
                <span>{preset.categoryLabel}</span>
                <span className="px-1.5 py-0.5 rounded bg-black/10 dark:bg-white/10">
                  {preset.expectedSla}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Main Submission Card */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`bg-white dark:bg-slate-900 rounded-3xl border transition-all shadow-lg p-6 sm:p-8 space-y-6 ${
          isDragOver
            ? "border-blue-500 ring-4 ring-blue-500/20 bg-blue-50/20 dark:bg-blue-950/20"
            : "border-slate-200/90 dark:border-slate-800"
        }`}
      >
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Step 1: Multimodal Evidence Capture */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-xs font-extrabold uppercase tracking-wider text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                <span className="w-5 h-5 rounded-full bg-blue-600 text-white flex items-center justify-center text-[10px]">1</span>
                <span>Attach Civic Evidence (Photo / Voice / Text)</span>
              </label>
              <span className="text-[11px] text-slate-400">Multimodal Intake Guard</span>
            </div>

            {/* Evidence Selector Tabs */}
            <div className="grid grid-cols-3 gap-2 sm:gap-3">
              {/* Take Photo Camera Button */}
              <button
                type="button"
                onClick={() => startLiveCamera()}
                className={`flex flex-col items-center justify-center p-3.5 rounded-2xl border-2 transition group cursor-pointer ${
                  isCameraOpen
                    ? "border-blue-600 bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 ring-2 ring-blue-400/40"
                    : "border-dashed border-slate-300 dark:border-slate-700 hover:border-blue-500 dark:hover:border-blue-400 hover:bg-blue-50/50 dark:hover:bg-blue-950/20 text-slate-700 dark:text-slate-300"
                }`}
              >
                <Camera className="w-5 h-5 text-blue-600 dark:text-blue-400 group-hover:scale-110 transition-transform mb-1" />
                <span className="text-xs font-bold">Take Photo</span>
                <span className="text-[10px] text-slate-400">Live Camera</span>
              </button>

              {/* Upload Image/Audio File Button */}
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className={`flex flex-col items-center justify-center p-3.5 rounded-2xl border-2 transition group cursor-pointer ${
                  file && !isCameraOpen
                    ? "border-indigo-600 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300"
                    : "border-dashed border-slate-300 dark:border-slate-700 hover:border-blue-500 dark:hover:border-blue-400 hover:bg-blue-50/50 dark:hover:bg-blue-950/20 text-slate-700 dark:text-slate-300"
                }`}
              >
                <UploadCloud className="w-5 h-5 text-indigo-600 dark:text-indigo-400 group-hover:scale-110 transition-transform mb-1" />
                <span className="text-xs font-bold">Upload File</span>
                <span className="text-[10px] text-slate-400">JPG, PNG, WebM</span>
              </button>

              {/* Record Voice Note Button */}
              <button
                type="button"
                onClick={isRecording ? stopRecording : startRecording}
                className={`flex flex-col items-center justify-center p-3.5 rounded-2xl border-2 transition group cursor-pointer ${
                  isRecording
                    ? "border-rose-500 bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 animate-pulse ring-2 ring-rose-400/40"
                    : "border-dashed border-slate-300 dark:border-slate-700 hover:border-blue-500 dark:hover:border-blue-400 hover:bg-blue-50/50 dark:hover:bg-blue-950/20 text-slate-700 dark:text-slate-300"
                }`}
              >
                {isRecording ? (
                  <Square className="w-5 h-5 text-rose-600 dark:text-rose-400 mb-1" />
                ) : (
                  <Mic className="w-5 h-5 text-purple-600 dark:text-purple-400 group-hover:scale-110 transition-transform mb-1" />
                )}
                <span className="text-xs font-bold">
                  {isRecording ? `Stop (${recordingDuration}s)` : "Voice Note"}
                </span>
                <span className="text-[10px] text-slate-400">
                  {isRecording ? "Recording audio..." : "Regional Speech"}
                </span>
              </button>
            </div>

            {/* Hidden Input for Desktop/Mobile File Upload */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*,audio/*,.jpg,.jpeg,.png,.webp,.gif,.bmp,.svg,.webm,.mp3,.wav,.ogg,.m4a"
              className="hidden"
              style={{ display: "none" }}
              onClick={(e) => {
                (e.target as HTMLInputElement).value = "";
              }}
              onChange={(e) => {
                const selected = e.target.files?.[0] ?? null;
                if (selected) {
                  if (selected.type.startsWith("audio/")) {
                    handleVoiceFileChange(selected);
                  } else {
                    handleFileChange(selected);
                  }
                }
              }}
            />

            {/* Hidden Input for Native Mobile Camera Fallback */}
            <input
              ref={cameraInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              style={{ display: "none" }}
              onClick={(e) => {
                (e.target as HTMLInputElement).value = "";
              }}
              onChange={(e) => {
                const selected = e.target.files?.[0] ?? null;
                if (selected) {
                  handleFileChange(selected);
                }
              }}
            />

            {/* LIVE WEBCAM & CAMERA VIEWFINDER MODAL/PANEL */}
            {isCameraOpen && (
              <div className="relative rounded-2xl overflow-hidden border-2 border-blue-500 bg-slate-950 shadow-2xl p-4 space-y-3 animate-fade-in">
                <div className="flex items-center justify-between text-white">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse" />
                    <span className="text-xs font-extrabold uppercase tracking-wider text-rose-400">
                      Live Camera Viewfinder
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={flipCamera}
                      className="p-2 rounded-xl bg-white/10 hover:bg-white/20 text-white transition text-xs font-bold flex items-center gap-1 cursor-pointer"
                      title="Switch Camera"
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                      <span className="hidden sm:inline">Flip</span>
                    </button>
                    <button
                      type="button"
                      onClick={stopLiveCamera}
                      className="p-2 rounded-xl bg-white/10 hover:bg-rose-600/80 text-white transition cursor-pointer"
                      title="Close Camera"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Camera Video Stream */}
                <div className="relative w-full h-64 sm:h-80 rounded-xl overflow-hidden bg-black flex items-center justify-center">
                  <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    muted
                    className={`w-full h-full object-cover ${facingMode === "user" ? "scale-x-[-1]" : ""}`}
                  />

                  {/* High-tech Viewfinder crosshairs */}
                  <div className="absolute inset-8 border border-white/20 rounded-xl pointer-events-none flex items-center justify-center">
                    <div className="w-6 h-6 border-t-2 border-l-2 border-blue-400 absolute top-0 left-0" />
                    <div className="w-6 h-6 border-t-2 border-r-2 border-blue-400 absolute top-0 right-0" />
                    <div className="w-6 h-6 border-b-2 border-l-2 border-blue-400 absolute bottom-0 left-0" />
                    <div className="w-6 h-6 border-b-2 border-r-2 border-blue-400 absolute bottom-0 right-0" />
                    <span className="text-[10px] text-white/50 font-mono tracking-widest uppercase">
                      AIM HAZARD EVIDENCE
                    </span>
                  </div>

                  {isCameraStarting && (
                    <div className="absolute inset-0 bg-black/80 flex flex-col items-center justify-center gap-2 text-white text-xs font-bold">
                      <span className="w-6 h-6 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                      <span>Initializing camera device...</span>
                    </div>
                  )}
                </div>

                {cameraError && (
                  <div className="p-3 rounded-xl bg-rose-950/80 border border-rose-800 text-rose-200 text-xs flex items-center justify-between">
                    <span>{cameraError}</span>
                    <button
                      type="button"
                      onClick={() => cameraInputRef.current?.click()}
                      className="ml-2 px-2.5 py-1 bg-white/20 hover:bg-white/30 rounded-lg text-xs font-bold shrink-0 cursor-pointer"
                    >
                      Browse Files
                    </button>
                  </div>
                )}

                {/* Shutter Capture Button */}
                <div className="flex items-center justify-center pt-1">
                  <button
                    type="button"
                    onClick={captureLivePhoto}
                    disabled={isCameraStarting}
                    className="px-6 py-3 rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-black text-xs uppercase tracking-wider flex items-center gap-2 shadow-lg shadow-blue-500/40 hover:scale-105 active:scale-95 transition-all cursor-pointer disabled:opacity-50"
                  >
                    <Camera className="w-4 h-4" />
                    <span>📸 Capture Photo</span>
                  </button>
                </div>
              </div>
            )}

            {/* Audio Waveform Live Visualizer while recording */}
            {isRecording && (
              <div className="p-3 bg-rose-50/90 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 rounded-2xl flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1 h-6">
                    <span className="w-1 bg-rose-600 rounded-full wave-bar-1" />
                    <span className="w-1 bg-rose-600 rounded-full wave-bar-2" />
                    <span className="w-1 bg-rose-600 rounded-full wave-bar-3" />
                    <span className="w-1 bg-rose-600 rounded-full wave-bar-4" />
                    <span className="w-1 bg-rose-600 rounded-full wave-bar-5" />
                  </div>
                  <span className="text-xs font-bold text-rose-800 dark:text-rose-200">
                    Listening to voice description... ({recordingDuration}s)
                  </span>
                </div>
                <button
                  type="button"
                  onClick={stopRecording}
                  className="px-3 py-1 bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold rounded-lg shadow-xs cursor-pointer"
                >
                  Done
                </button>
              </div>
            )}

            {/* HIGH-RES EVIDENCE PREVIEW BOX (IMAGE / AUDIO) */}
            {file && !isCameraOpen && (
              <div className="rounded-2xl overflow-hidden border-2 border-emerald-500/60 bg-slate-50 dark:bg-slate-900 p-4 space-y-3 shadow-md">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <span className="flex items-center justify-center w-6 h-6 rounded-full bg-emerald-500 text-white shadow-xs">
                      <CheckCircle2 className="w-4 h-4" />
                    </span>
                    <div>
                      <p className="text-xs font-black text-slate-900 dark:text-white truncate max-w-xs sm:max-w-md">
                        {file.name}
                      </p>
                      <p className="text-[11px] text-emerald-600 dark:text-emerald-400 font-bold">
                        ✓ Evidence Attached &amp; Verified · {(file.size / 1024).toFixed(1)} KB
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="px-3 py-1.5 text-xs font-bold rounded-xl bg-slate-200 hover:bg-slate-300 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 transition cursor-pointer"
                    >
                      Change File
                    </button>
                    <button
                      type="button"
                      onClick={() => handleFileChange(null)}
                      className="p-1.5 text-xs font-bold rounded-xl bg-rose-100 hover:bg-rose-200 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 transition cursor-pointer"
                      title="Remove file"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* High-Resolution Image Preview Window */}
                {filePreview ? (
                  <div className="w-full h-64 sm:h-80 rounded-xl overflow-hidden bg-slate-100 dark:bg-slate-950 flex items-center justify-center border border-slate-200 dark:border-slate-800 shadow-inner">
                    <img
                      src={filePreview}
                      alt="Uploaded Civic Evidence"
                      className="w-full h-full object-contain"
                    />
                  </div>
                ) : (
                  <div className="p-4 bg-purple-50 dark:bg-purple-950/40 rounded-xl border border-purple-200 dark:border-purple-800 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-purple-600 text-white flex items-center justify-center font-bold text-xs">
                      AUDIO
                    </div>
                    <div>
                      <p className="text-xs font-bold text-purple-900 dark:text-purple-200">
                        Voice Note Evidence File
                      </p>
                      <p className="text-[11px] text-purple-600 dark:text-purple-400">
                        Will be automatically transcribed by Multimodal Perception node
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Audio player preview */}
            {audioUrl && !filePreview && (
              <div className="pt-1">
                <audio src={audioUrl} controls className="w-full h-9 rounded-lg" />
              </div>
            )}
            {voiceFile && (
              <div className="flex items-center justify-between rounded-xl border border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-950/30 px-3 py-2">
                <span className="text-xs font-bold text-purple-800 dark:text-purple-200">
                  Voice description attached: {voiceFile.name}
                </span>
                <button
                  type="button"
                  onClick={() => handleVoiceFileChange(null)}
                  className="text-xs font-bold text-rose-600 hover:text-rose-800 cursor-pointer"
                >
                  Remove
                </button>
              </div>
            )}
          </div>

          {/* Description Textarea */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-extrabold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                Grievance Description
              </label>
              <span className="text-[11px] text-slate-400">
                Natural Language / Auto-Transcribed
              </span>
            </div>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Detail the issue: e.g. severe pothole on main road, overflowing garbage near school, high pressure water leakage..."
              rows={3}
              className="w-full border border-slate-300 dark:border-slate-700 rounded-2xl px-4 py-3 text-sm bg-slate-50/50 dark:bg-slate-800/50 focus:bg-white dark:focus:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition text-slate-900 dark:text-slate-100"
            />
          </div>

          {/* Step 2: Location Lock & City Selector */}
          <div className="space-y-3 pt-2 border-t border-slate-100 dark:border-slate-800">
            <div className="flex items-center justify-between">
              <label className="text-xs font-extrabold uppercase tracking-wider text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                <span className="w-5 h-5 rounded-full bg-blue-600 text-white flex items-center justify-center text-[10px]">2</span>
                <span>Incident Location (Pan-India)</span>
              </label>
              <button
                type="button"
                onClick={handleGetLocation}
                disabled={isLocating}
                className="text-xs font-bold text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 flex items-center gap-1 cursor-pointer disabled:opacity-50"
              >
                <Compass className={`w-3.5 h-3.5 ${isLocating ? "animate-spin" : ""}`} />
                <span>{isLocating ? "Acquiring GPS Lock..." : "Auto-Detect My GPS"}</span>
              </button>
            </div>

            {/* Pan-India Popular City Selector Quick-Pills */}
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] font-semibold text-slate-400 dark:text-slate-500 mr-1">
                Quick Cities:
              </span>
              {POPULAR_CITIES.map((c) => (
                <button
                  key={c.name}
                  type="button"
                  onClick={() => {
                    setGpsLat(c.lat);
                    setGpsLng(c.lng);
                    setLocationName(`${c.name} (${c.lat.toFixed(2)}, ${c.lng.toFixed(2)})`);
                  }}
                  className={`text-[11px] font-bold px-2.5 py-1 rounded-lg border transition-all cursor-pointer ${
                    locationName.includes(c.name)
                      ? "bg-blue-600 text-white border-blue-600 shadow-xs"
                      : "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700"
                  }`}
                >
                  {c.name}
                </button>
              ))}
            </div>

            {/* Coordinate Readout */}
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <MapPin className="absolute left-3.5 top-3 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  readOnly
                  value={
                    locationName ||
                    (gpsLat && gpsLng
                      ? `${gpsLat.toFixed(4)}° N, ${gpsLng.toFixed(4)}° E`
                      : "No coordinates attached (EXIF GPS or NLP landmark fallback will execute)")
                  }
                  className="w-full pl-9 pr-3 py-2.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-mono text-slate-700 dark:text-slate-300"
                />
              </div>
              {gpsLat && gpsLng && (
                <button
                  type="button"
                  onClick={() => {
                    setGpsLat(null);
                    setGpsLng(null);
                    setLocationName("");
                  }}
                  className="px-3 py-2 text-xs font-bold text-slate-400 hover:text-rose-600 transition cursor-pointer"
                >
                  Clear
                </button>
              )}
            </div>
            <p className="text-[11px] text-slate-400 dark:text-slate-500">
              Fallback chain: GPS device sensor &rarr; EXIF image metadata &rarr; Nominatim landmark lookup &rarr; Citizen pin prompt.
            </p>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="p-3.5 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 rounded-2xl flex items-start gap-2.5 text-xs text-rose-800 dark:text-rose-200">
              <AlertCircle className="w-4 h-4 text-rose-600 dark:text-rose-400 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Submit Action Button */}
          <button
            type="submit"
            disabled={isSubmitting || (!file && !description.trim())}
            className="w-full py-4 px-6 rounded-2xl font-black text-sm text-white bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-700 hover:from-blue-700 hover:via-indigo-700 hover:to-blue-800 shadow-lg shadow-blue-500/25 disabled:opacity-50 transition-all flex items-center justify-center gap-2 cursor-pointer group"
          >
            {isSubmitting ? (
              <>
                <span className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                <span>Compiling &amp; Dispatching to LangGraph Pipeline…</span>
              </>
            ) : (
              <>
                <span>Dispatch to CivicTriage Autonomous Graph</span>
                <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}

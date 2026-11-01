import React, { useState, useEffect } from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export default function OfflineNotice() {
  const [isOnline, setIsOnline] = useState<boolean>(navigator.onLine);
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState<boolean>(false);

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    const handleBeforeInstall = (e: Event) => {
      e.preventDefault();
      setInstallPrompt(e as BeforeInstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", handleBeforeInstall);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("beforeinstallprompt", handleBeforeInstall);
    };
  }, []);

  const handleInstallClick = async () => {
    if (!installPrompt) return;
    installPrompt.prompt();
    const { outcome } = await installPrompt.userChoice;
    if (outcome === "accepted") {
      setInstalled(true);
      setInstallPrompt(null);
    }
  };

  return (
    <>
      {/* Offline banner */}
      {!isOnline && (
        <div className="bg-amber-500 text-slate-900 px-4 py-2 text-xs font-bold flex items-center justify-between text-center sticky top-0 z-50 shadow-md">
          <div className="flex items-center gap-2 mx-auto">
            <span>📡</span>
            <span>You are currently offline. CivicTriage is running in Offline Cached Mode.</span>
          </div>
        </div>
      )}

      {/* PWA install prompt button */}
      {installPrompt && !installed && (
        <div className="fixed bottom-4 right-4 z-40 bg-slate-900 text-white border border-slate-700 shadow-2xl rounded-2xl p-3 flex items-center gap-3 text-xs animate-bounce">
          <span>📱 Install CivicTriage App</span>
          <button
            type="button"
            onClick={handleInstallClick}
            className="bg-blue-600 hover:bg-blue-700 text-white font-bold px-3 py-1.5 rounded-xl cursor-pointer"
          >
            Install
          </button>
          <button
            type="button"
            onClick={() => setInstallPrompt(null)}
            className="text-slate-400 hover:text-white px-1"
          >
            ✕
          </button>
        </div>
      )}
    </>
  );
}


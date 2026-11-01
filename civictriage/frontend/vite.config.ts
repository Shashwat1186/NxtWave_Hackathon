import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      // In dev, proxy API calls to local FastAPI backend
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: mode !== "production",
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          map: ["leaflet", "react-leaflet"],
          icons: ["lucide-react"],
        },
      },
    },
    // Increase chunk size warning limit slightly for map tiles
    chunkSizeWarningLimit: 1000,
  },
  define: {
    // Ensure NODE_ENV is set for libraries that need it
    "process.env.NODE_ENV": JSON.stringify(mode),
  },
}));

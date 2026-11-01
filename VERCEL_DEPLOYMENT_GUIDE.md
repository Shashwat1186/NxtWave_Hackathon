# 🚀 Vercel Production Deployment Guide: CivicTriage

This guide walks you through deploying the complete **CivicTriage** platform (React Vite Frontend + FastAPI Agentic Backend) to **Vercel** with zero friction.

---

## 🏛 Architecture Overview

| Component | Technology | Directory | Production Role |
| :--- | :--- | :--- | :--- |
| **Frontend** | React 18, Vite, TypeScript, Tailwind CSS, Leaflet | `civictriage/frontend/` | Citizen intake, public geospatial tracker, municipal admin SLA console |
| **Backend** | FastAPI, LangGraph, Google Gemini Multimodal, Motor MongoDB | `civictriage/backend/` | 8-Node Agentic Pipeline, Pan-India authority router, SSE streaming |

---

## ⚡ Deployment Methods

### Method 1: Monorepo Root Deployment (Easiest - 1 Click)

The repository root already includes a pre-configured `vercel.json` and `package.json`.

1. Push your repository to **GitHub**.
2. Go to [Vercel Dashboard](https://vercel.com/new) → **Add New Project** → Import your GitHub repository.
3. Keep **Root Directory** as `./` (default).
4. Vercel automatically detects the root configuration, executes `cd civictriage/frontend && npm install && npm run build`, and serves `civictriage/frontend/dist`.
5. Under **Environment Variables**, add:
   ```env
   VITE_API_BASE_URL=https://your-backend-service.vercel.app
   ```
6. Click **Deploy**.

---

### Method 2: Separate Frontend & Backend Projects (Recommended Microservices)

Deploying the frontend and backend as two linked Vercel projects gives you independent deployment pipelines and domain names.

#### Step 1: Deploy Backend (`civictriage/backend`)

1. Go to [Vercel Dashboard](https://vercel.com/new) → **Add New Project** → Select your repo.
2. In the configuration screen:
   - **Project Name**: `civictriage-backend`
   - **Framework Preset**: `Other`
   - **Root Directory**: Click **Edit** → Select `civictriage/backend`.
3. Add the **Environment Variables** (from your backend `.env`):
   | Variable | Example / Description | Required? |
   | :--- | :--- | :--- |
   | `MONGODB_URI` | `mongodb+srv://user:pass@cluster0.xxx.mongodb.net/?retryWrites=true&w=majority` | **Yes** |
   | `MONGODB_DB` | `civictriage` | **Yes** |
   | `GOOGLE_API_KEY` | `AIzaSy...` (from Google AI Studio) | **Yes** |
   | `LLM_PROVIDER` | `google` | **Yes** |
   | `LLM_PRIMARY_MODEL` | `gemini-1.5-flash` | **Yes** |
   | `LLM_FALLBACK_MODEL` | `gemini-1.5-pro` | **Yes** |
   | `EMBED_MODEL` | `models/gemini-embedding-001` | **Yes** |
   | `ADMIN_TOKEN` | `civic-admin-secret-2026-pass` | **Yes** |
   | `ENV` | `production` | **Yes** |
   | `DEBUG` | `false` | **Yes** |
   | `FRONTEND_URL` | `https://civictriage.vercel.app` (your frontend domain) | Optional |

4. Click **Deploy**.
5. Once deployed, note down your production backend URL (e.g., `https://civictriage-backend.vercel.app`).
6. Verify deployment by opening `https://civictriage-backend.vercel.app/health` in your browser. You should receive:
   ```json
   {"status":"ok","demo_mode":false,"env":"production"}
   ```

---

#### Step 2: Deploy Frontend (`civictriage/frontend`)

1. Go to [Vercel Dashboard](https://vercel.com/new) → **Add New Project** → Select the same repo.
2. In the configuration screen:
   - **Project Name**: `civictriage`
   - **Framework Preset**: `Vite`
   - **Root Directory**: Click **Edit** → Select `civictriage/frontend`.
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
3. Add the **Environment Variables**:
   | Variable | Value | Description |
   | :--- | :--- | :--- |
   | `VITE_API_BASE_URL` | `https://civictriage-backend.vercel.app` | URL of your deployed backend from Step 1 |

4. Click **Deploy**.
5. Your production CivicTriage UI is live!

---

## 🛠 Pre-configured Vercel Files Included in Codebase

| File | Purpose |
| :--- | :--- |
| `vercel.json` (Root) | Monorepo build orchestrator routing build commands to the Vite frontend. |
| `civictriage/frontend/vercel.json` | Single-Page Application (SPA) fallback routing (`/*` → `/index.html`), caching headers for assets, security headers (`X-Frame-Options`, `X-Content-Type-Options`). |
| `civictriage/backend/vercel.json` | Directs all API incoming routes to `@vercel/python` serverless handler with edge CORS headers. |
| `civictriage/backend/api/index.py` | Native Vercel Serverless Function entry point exporting the ASGI FastAPI `app`. |
| `civictriage/backend/Procfile` & `Dockerfile` | Alternative production deployment presets for container platforms (Railway, Render, Fly.io, Google Cloud Run). |

---

## 🔒 Security & CORS Configurations

- In `civictriage/backend/app/main.py`, CORS is dynamically configured to allow requests from `localhost` in development and any `*.vercel.app` preview/production domain in production.
- Security headers (`nosniff`, `DENY` clickjacking, `X-XSS-Protection`) are pre-applied via `vercel.json`.
- Filesystem uploads on Vercel automatically redirect to the writable `/tmp/uploads` directory.

---

## ✅ Deployment Verification Checklist

- [x] **Frontend Builds Without Errors**: `npm run build` completed successfully (`dist/` generated with code-splitting).
- [x] **TypeScript Strict Check**: `tsc --noEmit` exits with `0` errors.
- [x] **Vercel SPA Rewrites**: Configured in `vercel.json` so refreshing routes like `/dashboard`, `/admin`, and `/issues/:id` does not return 404.
- [x] **API URLs Configured**: Both `client.ts` and `useSSE.ts` safely read `VITE_API_BASE_URL` with automatic trailing slash normalization.
- [x] **CORS Middleware Active**: Accepts production requests from Vercel subdomains.
- [x] **Resilient MongoDB Fallback**: In-memory mock database activates automatically if Atlas is temporarily unreachable, ensuring 100% demo uptime.


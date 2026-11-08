# MethaTrace

MethaTrace is a pipeline monitoring prototype with a **Next.js frontend** and a **FastAPI backend**. The backend loads the shared synthetic pipeline and methane datasets, provides risk, methane, sensor and report APIs, and hosts the Gemini-powered AI Analyst. The frontend calls the backend over HTTP.

## Requirements

- Python 3.11 or newer
- Node.js and npm
- A Gemini Developer API key to enable the AI Analyst

## Install

From the repository root, install the Python dependencies:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS/Linux, activate the environment with `source venv/bin/activate`.

Install the frontend dependencies:

```powershell
cd frontend
npm install
cd ..
```

## Configure Gemini

Copy `.env.example` to `.env` in the repository root. Set:

```env
AI_ENABLED=true
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.5-flash
```

The Gemini key is backend-only; do not place it in a `NEXT_PUBLIC_` variable. Restart FastAPI after changing `.env`. The AI Analyst returns a clear unavailable response when AI is disabled or credentials are not configured.

`CORS_ORIGINS` is a comma-separated list of exact browser origins allowed to call FastAPI. The defaults in `.env.example` are for local development. Before deployment, set it to the deployed frontend origin(s); wildcard origins are rejected while credentialed CORS is enabled.

## Run both servers

Start FastAPI from the repository root in one terminal:

```powershell
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Start Next.js from `frontend/` in a second terminal:

```powershell
npm run dev
```

Open <http://localhost:3000>. The frontend uses `http://127.0.0.1:8000` by default. To use another backend URL, set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` and restart Next.js.

For deployment, configure `NEXT_PUBLIC_API_URL` at frontend build time to the public FastAPI base URL, and configure `CORS_ORIGINS` on the backend with the exact deployed frontend origin. Keep `GEMINI_API_KEY` only in the backend environment.

FastAPI health is available at <http://127.0.0.1:8000/api/health>; interactive API documentation is at <http://127.0.0.1:8000/docs>.

## Verification

From the repository root, run backend tests:

```powershell
python -m pytest
```

For frontend checks, run these commands from `frontend/`:

```powershell
npm run lint
npx tsc --noEmit
npm run build
```

## Repository layout

- `frontend/` — Next.js dashboard routes, shared components, maps, and themes.
- `backend/` — FastAPI routes and the Gemini AI Analyst adapter.
- `utils/` — shared data loading, pipeline processing, risk assessment, sensor simulation, weather, and PDF report services.
- `data/` — synthetic pipeline GeoJSON and methane observation datasets.
- `scripts/` — data generation and validation tools.

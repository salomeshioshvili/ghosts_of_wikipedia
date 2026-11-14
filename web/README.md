# Frontend (Person 2)

React + Vite + TypeScript app for Ghosts of Wikipedia.

    npm install
    npm run dev          # http://localhost:5173 ; /api is proxied to FastAPI on http://localhost:8000

Mock data: `src/lib/api.ts` has `USE_MOCK`. Set it to `false` to use the real API
(start it from the repo root: `python -m uvicorn api.main:app --port 8000`).
`npm run build` writes `web/dist`, which the API serves at `/` in production.

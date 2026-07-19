# STRATUM Backend

FastAPI backend for EdStratum Labs' STRATUM AI Strategy Intake and Discovery Advisor.

The service is designed for the existing React/Vite frontend on Cloudflare Pages. It exposes:

- `POST /api/chat` as a Server-Sent Events stream matching the Phase 1 `StreamEvent` union.
- `GET /api/health` for platform health checks.
- Local deterministic generation for development and CI when LLM credentials are absent.
- Optional Resend notification side effects when escalation credentials are configured.

## Run Locally

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/api/health
```

SSE smoke test:

```bash
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Does AI make sense for my Canvas environment?","timestamp":0}],"mode":"open","intakeIndex":null,"intakeAnswers":{},"sessionId":"local-smoke"}'
```

## Environment

Copy `.env.example` to `.env` for local development. The backend starts without provider keys and uses deterministic fallback responses so contract tests can run offline.

Production variables:

- `OPENAI_API_KEY`: optional for future LLM-backed generation.
- `RESEND_API_KEY`: enables escalation emails.
- `JEFFREY_EMAIL`: destination for escalation emails.
- `ALLOWED_ORIGINS`: comma-separated CORS origins.
- `CONFIDENCE_THRESHOLD`: default `0.55`.
- `CALENDLY_URL`: direct booking URL.

## Deployment Status

Backend deployment needs a Python-capable host such as Railway, Fly.io, or a VPS. This workspace does not currently contain Railway/Fly credentials or a connected frontend source repo. Cloudflare Pages access is available through the sensitive handoff, but it should not be mutated until a production backend URL exists.

The frontend contract attachment also clarifies that Phase 1 has no HTTP/SSE fetch adapter yet. Before the Cloudflare redeploy, apply the code in `frontend-integration/` to the real frontend source so `STRATUM_BACKEND_ENABLED` routes to the backend instead of always calling the mock generator.

Use the read-only preflight before any deploy handoff:

```bash
./scripts/deployment_readiness.sh
```

After the backend is deployed, set `VITE_STRATUM_API_URL` as a Cloudflare Pages production build-time environment variable and redeploy the frontend from a workspace containing the React/Vite source or a verified `dist/` artifact. Use `scripts/set_cloudflare_pages_env.sh` for the env var, `scripts/verify_frontend_seo.sh` for SEO checks, and `deploy/README.md` for the deployment order.

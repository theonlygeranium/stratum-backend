# STRATUM Backend

FastAPI backend for EdStratum Labs' STRATUM AI Strategy Intake and Discovery Advisor.

The service is designed for the existing React/Vite frontend on Cloudflare Pages. It exposes:

- `POST /api/chat` as a Server-Sent Events stream matching the Phase 1 `StreamEvent` union.
- `GET /api/health` for platform health checks.
- LangGraph-based routing for open Q&A, intake, about, and escalation modes.
- Hybrid RAG retrieval with `rank_bm25`, Chroma-backed dense retrieval, RRF fusion, and configurable reranking.
- Local deterministic embeddings/generation for development and CI when provider credentials are absent.
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

Required demo variables:

- `OPENAI_API_KEY`: enables OpenAI-compatible generation and, when `EMBEDDING_PROVIDER=openai`, OpenAI embeddings.
- `DATABASE_URL`: enables Postgres-backed session state and LangGraph checkpoint attempts.
- `RESEND_API_KEY`: enables escalation emails.
- `JEFFREY_EMAIL`: destination for escalation emails.
- `ALLOWED_ORIGINS`: comma-separated CORS origins.

Useful optional variables:

- `CONFIDENCE_THRESHOLD`: default `0.55`.
- `CALENDLY_URL`: direct booking URL.
- `EMBEDDING_PROVIDER`: `hash` for deterministic local/demo embeddings, or `openai`.
- `EMBEDDING_MODEL`: default `text-embedding-3-small`.
- `VECTOR_STORE_PROVIDER`: `chroma` by default, falling back to memory if Chroma is unavailable.
- `CHROMA_PERSIST_DIR`: optional path for persistent local Chroma storage.
- `RERANKER_PROVIDER`: `heuristic` for demo/local, or `cohere` to use Cohere's rerank API when `COHERE_API_KEY` is configured.
- `RERANKER_MODEL`: default `rerank-v4.0-fast`.

## Verification

Run the local contract, graph, conversation, and RAG tests:

```bash
.venv/bin/pytest -q
```

Run the RAG acceptance harness:

```bash
.venv/bin/python scripts/eval_rag.py --json
```

Current local targets:

- Retrieval Recall@10: `>= 0.90`.
- Groundedness proxy: `>= 0.85`.
- No-key first-token latency: `< 1500ms`.

## Deployment Status

The backend is deployed on Railway at:

```text
https://stratum-backend-production-a340.up.railway.app
```

Cloudflare Pages serves the frontend at `https://edstratumlabs.ai` and the live STRATUM bundle points to the Railway backend URL. See `CLOUDFLARE_DEPLOY_STATUS.md` for the latest checked deployment evidence.

# STRATUM Backend

FastAPI backend for EdStratum Labs' STRATUM AI Strategy Intake and Discovery Advisor.

The service is designed for the existing React/Vite frontend on Cloudflare Pages. It exposes:

- `POST /api/chat` as a Server-Sent Events stream matching the Phase 1 `StreamEvent` union.
- `GET /api/health` for platform health checks.
- `GET /api/runtime` for non-secret runtime diagnostics.
- LangGraph-based routing for open Q&A, intake, about, and escalation modes.
- Hybrid RAG retrieval with `rank_bm25`, Chroma-backed dense retrieval, RRF fusion, and configurable reranking.
- OpenAI-compatible provider streaming for grounded answers, with deterministic fallback token streaming when provider credentials are absent.
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

Runtime diagnostics:

```bash
curl http://localhost:8000/api/runtime
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

- `WRITER_API_KEY`: enables WRITER Palmyra chat generation. The default chat endpoint is `https://api.writer.com/v1/chat/completions` with model `palmyra-x5`.
- `DATABASE_URL`: enables Postgres-backed session state and LangGraph checkpoint attempts.
- `RESEND_API_KEY`: enables escalation emails.
- `ESCALATION_EMAIL_TO`: destination for escalation emails.
- `ESCALATION_EMAIL_FROM`: optional sender address. Defaults to
  `stratum@edstratumlabs.ai` and falls back to Resend's default sender if the
  domain sender is not accepted. Legacy `JEFFREY_EMAIL` and
  `RESEND_FROM_EMAIL` aliases are still accepted for older Railway projects.
- `ALLOWED_ORIGINS`: comma-separated CORS origins.

Useful optional variables:

- `CONFIDENCE_THRESHOLD`: default `0.55`.
- `CALENDLY_URL`: optional booking URL. Leave blank until scheduling is provisioned.
- `LLM_PROVIDER`: default `writer`. Set to `openai` only for an explicit OpenAI chat override.
- `LLM_BASE_URL`: default `https://api.writer.com/v1/chat/completions`.
- `LLM_MODEL`: default `palmyra-x5`.
- `LLM_API_KEY`: optional generic generation key fallback. `WRITER_API_KEY` takes precedence for default Palmyra generation.
- `OPENAI_API_KEY`: optional for OpenAI embeddings, or for chat only when `LLM_PROVIDER=openai` or `LLM_BASE_URL` points to OpenAI.
- `EMBEDDING_PROVIDER`: default `hash`. Set to `openai` only when
  `OPENAI_API_KEY` is separately configured for embeddings.
- `EMBEDDING_MODEL`: default `text-embedding-3-small`.
- `VECTOR_STORE_PROVIDER`: `chroma` by default. Set to `pinecone` only with
  `PINECONE_API_KEY` and `PINECONE_INDEX`; setup falls back to Chroma or memory
  if the managed vector store is unavailable.
- `CHROMA_PERSIST_DIR`: optional path for persistent local Chroma storage.
- `PINECONE_NAMESPACE`: optional namespace for isolating staging/production KB
  vectors in a shared Pinecone index.
- `RERANKER_PROVIDER`: leave unset/blank for auto mode (`cohere` when
  `COHERE_API_KEY` is present, otherwise `heuristic`), or set explicitly.
- `RERANKER_MODEL`: default `rerank-v4.0-fast`.
- `ELEVENLABS_API_KEY`: optional server-side key for `/api/tts`.
- `ELEVENLABS_VOICE_ID`: optional ElevenLabs voice override.

## Verification

Run the local contract, graph, conversation, and RAG tests:

```bash
.venv/bin/pytest -q
```

Run the RAG acceptance harness:

```bash
.venv/bin/python scripts/eval_rag.py --json
```

Run the deployed Phase 4 conversation matrix:

```bash
.venv/bin/python scripts/eval_deployed_conversations.py --json
```

Run the safe deployed backend smoke:

```bash
.venv/bin/python scripts/live_backend_smoke.py
```

The smoke checks public `/api/health`, production CORS, `/api/runtime`, one
grounded RAG SSE stream, and one `X-Stratum-Eval: true` suppressed escalation
SSE stream. It does not send live handoff email.

Run the non-mutating release/governance audit:

```bash
.venv/bin/python scripts/live_release_audit.py
```

The release audit checks GitHub `main` branch protection, required status/check
state, Cloudflare Pages deployment state, the live frontend manifest and runtime
flags, Railway deployment status, and backend health/runtime. It reports only
safe metadata and exits nonzero while governance or control-plane blockers
remain.

To include the safe deployed Phase 4 matrix from the original SOT, add:

```bash
.venv/bin/python scripts/live_release_audit.py --include-conversation-matrix
```

That opt-in gate runs the 50+ scenario SSE conversation suite with
`X-Stratum-Eval: true`, so escalation checks are suppressed and no live handoff
email is sent.

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

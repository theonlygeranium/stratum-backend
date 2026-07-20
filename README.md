<div align="center">

# STRATUM Backend

### FastAPI + LangGraph AI advisor for EdStratum Labs — deployed on Railway

[![Live API](https://img.shields.io/badge/API-stratum--backend--production--a340.up.railway.app-7c3aed?style=flat-square&logo=fastapi&logoColor=white)](https://stratum-backend-production-a340.up.railway.app/api/health)
[![Backend CI](https://img.shields.io/github/actions/workflow/status/theonlygeranium/stratum-backend/backend-ci.yml?branch=main&style=flat-square&label=Backend%20CI)](https://github.com/theonlygeranium/stratum-backend/actions)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](#license)

**FastAPI** · **Python 3.11** · **LangGraph** · **Chroma** · **rank_bm25** · **Writer Palmyra** · **Railway** · **pytest**

</div>

---

## Overview

This is the backend service powering **StratumChat**, EdStratum Labs' AI Strategy Intake & Discovery Advisor. It is a FastAPI application deployed on Railway at **[stratum-backend-production-a340.up.railway.app](https://stratum-backend-production-a340.up.railway.app)**.

The backend implements a LangGraph-based conversation router that handles open Q&A, structured intake discovery, escalation handoffs, and about/informational queries. It grounds responses using hybrid retrieval-augmented generation (RAG): BM25 sparse retrieval fused with Chroma-backed dense retrieval via reciprocal rank fusion (RRF), with optional reranking. Generation streams through Writer's Palmyra model with a deterministic fallback when provider credentials are absent — so the full test suite runs offline in CI.

> **Design principle:** The backend starts without any provider keys and uses deterministic fallback responses for generation, embeddings, and vector storage. This keeps contract tests fully offline while production upgrades transparently to Writer (LLM), OpenAI (embeddings), Pinecone (vector store), and ElevenLabs (TTS) when the corresponding environment variables are set.

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|--------|
| Framework | FastAPI | async ASGI |
| Language | Python | 3.11 |
| Agent orchestration | LangGraph | graph-based routing |
| Sparse retrieval | rank_bm25 | BM25 |
| Dense retrieval | Chroma | local vector store (Pinecone optional) |
| Fusion | RRF | reciprocal rank fusion |
| Reranking | Cohere / heuristic | auto-selected |
| LLM generation | Writer Palmyra | `palmyra-x5` (deterministic fallback) |
| Embeddings | hash (local) / OpenAI | `text-embedding-3-small` |
| Email | Resend | escalation handoff notifications |
| TTS | ElevenLabs | optional `/api/tts` proxy |
| Hosting | Railway | auto-deploy from `main` |
| Testing | pytest | 138 tests + RAG eval harness |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat` | SSE-streamed chat conversation (Phase 1 `StreamEvent` union) |
| `GET` | `/api/health` | Platform health check (RAG, TTS status) |
| `GET` | `/api/runtime` | Non-secret runtime diagnostics (providers, graph runtime) |
| `POST` | `/api/escalate` | Escalation email handoff via Resend |
| `POST` | `/api/tts` | Text-to-speech proxy to ElevenLabs |

---

## Quick Start

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

---

## Environment

Copy `.env.example` to `.env` for local development. The backend starts without provider keys and uses deterministic fallback responses so contract tests run offline.

### Production Variables

| Variable | Purpose |
|----------|--------|
| `WRITER_API_KEY` | Enables Writer Palmyra chat generation (`palmyra-x5`) |
| `DATABASE_URL` | Enables Postgres-backed session state and LangGraph checkpointing |
| `RESEND_API_KEY` | Enables escalation emails |
| `ESCALATION_EMAIL_TO` | Destination for escalation emails |
| `ESCALATION_EMAIL_FROM` | Optional sender (defaults to `stratum@edstratumlabs.ai`) |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins |

### Optional Provider Variables

| Variable | Purpose |
|----------|--------|
| `OPENAI_API_KEY` | OpenAI embeddings or chat override |
| `EMBEDDING_PROVIDER` | `hash` (default) or `openai` |
| `VECTOR_STORE_PROVIDER` | `chroma` (default) or `pinecone` |
| `PINECONE_API_KEY` / `PINECONE_INDEX` | Managed vector store |
| `LLM_PROVIDER` / `LLM_BASE_URL` / `LLM_MODEL` | Chat provider override |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | TTS |
| `RERANKER_PROVIDER` / `RERANKER_MODEL` | `cohere`, `heuristic`, or auto |
| `CONFIDENCE_THRESHOLD` | Default `0.55` |
| `CALENDLY_URL` | Optional booking URL (leave blank until provisioned) |

---

## Verification

```bash
# Full test suite
.venv/bin/pytest -q

# RAG acceptance harness
.venv/bin/python scripts/eval_rag.py --json

# Deployed Phase 4 conversation matrix
.venv/bin/python scripts/eval_deployed_conversations.py --json

# Safe deployed backend smoke (no live email)
.venv/bin/python scripts/live_backend_smoke.py

# Non-mutating release/governance audit
.venv/bin/python scripts/live_release_audit.py
.venv/bin/python scripts/live_release_audit.py --include-conversation-matrix
```

### Current Local Targets

- Retrieval Recall@10: `>= 0.90`
- Groundedness proxy: `>= 0.85`
- No-key first-token latency: `< 1500ms`

### Activation Profiles

```bash
.venv/bin/python scripts/live_release_audit.py --activation-profile managed-rag
.venv/bin/python scripts/live_release_audit.py --activation-profile voice
.venv/bin/python scripts/live_release_audit.py --activation-profile persistence
.venv/bin/python scripts/live_release_audit.py --activation-profile edge-voice
.venv/bin/python scripts/live_release_audit.py --activation-profile full-activation
```

Profiles are non-mutating expectation bundles:

- **`current`**: today's gated-off production runtime
- **`managed-rag`**: expects `embedding_provider=openai` and `vector_store_provider=pinecone`
- **`voice`**: expects frontend `voiceEnabled=true` and backend `tts.status=ok`
- **`persistence`**: expects frontend `persistenceEnabled=true`
- **`edge-voice`**: expects voice + persistence on while keeping managed RAG on hash/Chroma
- **`full-activation`**: combines managed RAG, voice, and persistence

---

## Deployment

The backend deploys on Railway via GitHub-connected auto-deploy:

```text
https://stratum-backend-production-a340.up.railway.app
```

### Direct Deploy Fallback

If GitHub-backed Railway deployment is unavailable during an urgent release:

```bash
CONFIRM_DIRECT_RAILWAY_DEPLOY=yes ./scripts/railway_direct_deploy.sh
```

The helper deploys the current local source tree with `railway up`, polls until terminal state, and runs `live_backend_smoke.py` after success. Copy any urgent direct-deployed source back to GitHub afterward.

---

## Related Repository

| Repository | Description |
|-----------|-------------|
| [edstratum-v2-frontend](https://github.com/theonlygeranium/edstratum-v2-frontend) | React 19 + Vite 6 SPA on Cloudflare Pages — StratumChat UI, citations, voice, PDF |

---

## License

MIT

# STRATUM Deploy Status

Checked on 2026-07-19 after the Railway-backed STRATUM deployment.

## Backend

- GitHub repository: `theonlygeranium/stratum-backend`
- Branch: `main`
- Latest verified application commit: `83cac9c18568631daff4936e3e56aee25dddbced`
- Railway project/environment: `sunny-ambition / production`
- Railway deployment id: `5514989950`
- Railway status: `success`
- Public backend URL: `https://stratum-backend-production-a340.up.railway.app`
- Health check: `GET /api/health` returns `{"status":"healthy","stratum":"online","backend_enabled":true}`

## Cloudflare Pages

- Pages project: `edstratumlabs`
- Production aliases: `https://edstratumlabs.ai`, `https://www.edstratumlabs.ai`
- Pages deployment id: `820a3bbe-ba74-4f80-9e44-dc2e11b1aa5d`
- Pages deployment status: `success`
- Production build-time env var: `VITE_STRATUM_API_URL=https://stratum-backend-production-a340.up.railway.app`
- Live STRATUM chunk includes the Railway URL, `/api/chat`, `fetch(...)`, and `Accept: text/event-stream`.

## Verification

- Backend test suite: `73 passed, 1 warning`
- Docker build: passed with the Railway-compatible `${PORT:-8000}` command.
- Secret/token scan: no matches in tracked backend source.
- Live backend SSE smoke test: passed for open/about/escalation paths after commit `83cac9c`.
- Live CORS preflight from `https://edstratumlabs.ai`: passed.
- Live frontend SEO tags: meta description, canonical, OG title, and OG description present.
- Live static files: `/robots.txt`, `/sitemap.xml`, `/og-image.png`, `/_headers`, and `/_redirects` all return HTTP 200.

## Remaining Strict Spec Gaps

- The backend emits valid SSE chunks, but model/provider streaming is not wired end to end; responses are composed first and then emitted as token chunks.
- `app/graph.py` contains state helpers, but the request path is not yet a compiled LangGraph `StateGraph` with node/edge orchestration or `PostgresSaver` checkpoints.
- Retrieval is local hybrid scoring with RRF-style fusion and heuristic reranking. OpenAI embeddings, Chroma/Pinecone/Qdrant storage, and cross-encoder reranking are still architectural gaps.
- Acceptance metrics such as retrieval Recall@10, groundedness percentage, latency targets, escalation rate, and abandonment are not yet measured against production traffic or a formal eval harness.

## Notes

- The local shell is not authenticated to Railway. GitHub deployment statuses confirm Railway production deploy success and expose the public service domain.
- The Railway API values provided during handoff did not authorize as Railway bearer tokens, so service variable values were not listed locally.
- Cloudflare credentials remain only in the sensitive handoff attachment and were not committed to this repository.

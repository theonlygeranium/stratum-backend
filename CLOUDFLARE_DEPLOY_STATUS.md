# STRATUM Deploy Status

Checked on 2026-07-19 after the Railway-backed STRATUM deployment.

## Backend

- GitHub repository: `theonlygeranium/stratum-backend`
- Branch: `main`
- Railway project/environment: `sunny-ambition / production`
- Railway deployment status: verified after each backend push through GitHub deployment status and live health checks.
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

- Backend test suite: `85 passed, 1 skipped, 2 warnings`
- Optional Postgres checkpoint smoke: passed locally with `STRATUM_TEST_DATABASE_URL`.
- RAG acceptance harness: passed locally with Recall@10 `1.0`, groundedness proxy `1.0`, and no-key first-token latency under `1500ms`.
- Deployed Phase 4 conversation matrix: `54` live turns passed with contract pass rate `1.0`, expected behavior `1.0`, persona consistency `1.0`, no-hallucination proxy `1.0`, snapshot delivery `1.0`, scripted escalation rate `0.2222`, abandonment proxy `0.0`, and first-token latency p95 `1161.58ms`.
- OpenAI-compatible provider streaming path: covered by parser and progressive-stream contract tests.
- Docker build: passed with the Railway-compatible `${PORT:-8000}` command.
- Secret/token scan: no matches in tracked backend source.
- Live backend SSE smoke test: passed for open/about/escalation paths.
- Live progressive streaming spot check: first SSE event in `48-60ms`; first-token timings `903ms`, `754ms`, `48ms`, and `245ms` across Canvas, strategy, about, and escalation prompts.
- Live CORS preflight from `https://edstratumlabs.ai`: passed.
- Live frontend SEO tags: meta description, canonical, OG title, and OG description present.
- Live static files: `/robots.txt`, `/sitemap.xml`, `/og-image.png`, `/_headers`, and `/_redirects` all return HTTP 200.

## Remaining Strict Spec Gaps

- LangGraph routing and optional PostgresSaver checkpoint support are implemented, but production checkpoint table creation still needs Railway runtime verification with `DATABASE_URL`.
- LangGraph topology is compressed into route/open/intake/about/escalation nodes; the spec's explicit `rag`, `assess`, `generate`, and `notify` nodes remain a strict-architecture hardening item.
- Retrieval now uses `rank_bm25`, Chroma-backed dense retrieval, RRF-style fusion, heuristic reranking by default, and an optional Cohere cross-encoder reranker when `RERANKER_PROVIDER=cohere` plus `COHERE_API_KEY` are configured. The demo Railway env does not require Cohere.
- Acceptance metrics now run locally through `scripts/eval_rag.py` and against Railway through `scripts/eval_deployed_conversations.py`; passive production traffic analytics for real visitor escalation and abandonment remain uninstrumented.

## Notes

- Railway CLI agent support and the `use-railway` skill are installed. The local CLI is not OAuth-authenticated, but the custom Railway MCP can list the project and check service health.
- Custom Railway MCP project read confirms project `sunny-ambition`, service `stratum-backend`, Postgres service `postgres`, and environment `production`. Some custom MCP deployment/domain/env-var reads currently fail against Railway GraphQL schema fields.
- Cloudflare credentials remain only in the sensitive handoff attachment and were not committed to this repository.

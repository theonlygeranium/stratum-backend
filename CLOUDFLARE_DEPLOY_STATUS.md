# STRATUM Deploy Status

Checked on 2026-07-20 after the Railway-backed STRATUM deployment and graph-backed SSE refresh.

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
- Live lazy STRATUM chunk (`StratumChat-cfHiQN2_.js` as of this check) includes the Railway URL, `/api/chat`, `fetch(...)`, and `Accept: text/event-stream`.

## Verification

- Backend test suite: `106 passed, 1 skipped, 2 warnings`
- Optional Postgres checkpoint smoke: passed locally with `STRATUM_TEST_DATABASE_URL`.
- RAG acceptance harness: `20` local golden questions passed with Recall@10 `1.0`, groundedness proxy `1.0`, retrieval p50 `1.97ms` / p95 `2.90ms`, and no-key first-token latency `11.32ms`.
- `/api/chat` SSE now uses the compiled LangGraph runtime for direct escalation, intake, about, and open Q&A. Open Q&A streams the graph-prepared retrieval/source state before LLM tokens, then checkpoints the generated result through the graph `generate` node.
- Escalation handoff copy is notification-status-aware: it says a summary was sent only when the Resend/log handoff succeeds, and otherwise says a summary was prepared.
- Direct escalation routing now uses phrase-level handoff requests rather than broad single-word triggers, with sentiment/frustration detection taking priority for documented frustration phrases.
- Deployed Phase 4 conversation matrix: `54` live turns passed with contract pass rate `1.0`, expected behavior `1.0`, persona consistency `1.0`, no-hallucination proxy `1.0`, snapshot delivery `1.0`, scripted escalation rate `0.2222`, abandonment proxy `0.0`, and first-token latency p50 `53.98ms` / p95 `1184.77ms` / max `4872.71ms`.
- OpenAI-compatible provider streaming path: covered by parser and progressive-stream contract tests.
- Docker build: passed with the Railway-compatible `${PORT:-8000}` command.
- Secret/token scan: no matches in tracked backend source.
- Live backend SSE smoke test: passed for open/about/escalation paths.
- Live progressive streaming spot check: graph-backed open Q&A emitted `searching`, `retrieving`, `composing`, `source`, then tokens; first SSE event in `102.36ms`.
- Live CORS preflight from `https://edstratumlabs.ai`: passed.
- Live frontend SEO tags: meta description, canonical, OG title, and OG description present.
- Live static files: `/robots.txt`, `/sitemap.xml`, `/og-image.png`, `/_headers`, and `/_redirects` all return HTTP 200.

## Remaining Strict Spec Gaps

- LangGraph routing now exposes the executable spec topology: `route`, `open`, `intake`, `assess`, `about`, `escalation`, `notify`, and shared terminal `generate`; optional PostgresSaver checkpoint support is implemented, but production checkpoint table creation still needs Railway runtime verification with `DATABASE_URL`.
- Diagram-level `rag`, `persona`, and `handoff` stages remain consolidated into branch handlers. Open-mode retrieval and generation are separated for SSE/checkpointing, but the graph still does not expose every diagram label as its own node.
- Retrieval now uses `rank_bm25`, Chroma-backed dense retrieval, RRF-style fusion, and auto-selects OpenAI embeddings when `OPENAI_API_KEY` is present; no-key local/demo runs use deterministic hash embeddings.
- Reranking auto-selects Cohere cross-encoder reranking when `COHERE_API_KEY` is present; no-key local/demo runs use heuristic reranking. The demo Railway env does not require Cohere.
- Acceptance metrics now run locally through `scripts/eval_rag.py` and against Railway through `scripts/eval_deployed_conversations.py`; passive production traffic analytics for real visitor escalation and abandonment remain uninstrumented.

## Notes

- Railway CLI agent support and the `use-railway` skill are installed and up to date. The official local MCP is configured; OAuth login is required for `railway agent`.
- Custom Railway MCP is configured in Codex as `railway-mcp` with bearer auth via `RAILWAY_CUSTOM_MCP_BEARER_TOKEN`; direct MCP verification returned server `railway_mcp` version `1.28.1` and all `9` tools.
- Cloudflare credentials remain only in the sensitive handoff attachment and were not committed to this repository.

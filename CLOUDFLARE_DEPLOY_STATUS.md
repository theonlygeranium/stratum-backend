# STRATUM Deploy Status

Checked on 2026-07-20 after the Railway-backed STRATUM deployment,
runtime-diagnostics pass, OpenAI embedding wiring fix, Resend sender fallback,
and discretion-safe escalation copy update.

## Backend

- GitHub repository: `theonlygeranium/stratum-backend`
- Branch: `main`
- Railway project/environment: `sunny-ambition / production`
- Latest verified code commit: `f1c390f`
- Railway deployment status: `success` for `sunny-ambition - stratum-backend`
  through GitHub deployment status and live health/runtime checks.
- Public backend URL: `https://stratum-backend-production-a340.up.railway.app`
- Health check: `GET /api/health` returns `{"status":"healthy","stratum":"online","backend_enabled":true}`
- Runtime diagnostics: `GET /api/runtime` reports `graph_runtime=langgraph`,
  `checkpointer=postgres`, `database_configured=true`,
  `session_store_backend=postgres`, `embedding_provider=openai`,
  `vector_store_provider=chroma`, `llm_configured=true`,
  `openai_api_key_configured=true`, `notifications_configured=true`,
  `escalation_email_configured=true`,
  `allowed_origins_env_configured=true`, and
  `required_cors_origins_present=true`.
- Production escalation routing: `JEFFREY_EMAIL` is set in Railway to the
  private owner inbox supplied out-of-band; `CALENDLY_URL` is intentionally blank
  until a scheduling link is provisioned.

## Cloudflare Pages

- Pages project: `edstratumlabs`
- Production aliases: `https://edstratumlabs.ai`, `https://www.edstratumlabs.ai`
- Pages deployment id: `820a3bbe-ba74-4f80-9e44-dc2e11b1aa5d`
- Pages deployment status: `success`
- Production build-time env var: `VITE_STRATUM_API_URL=https://stratum-backend-production-a340.up.railway.app`
- Live lazy STRATUM chunk (`StratumChat-cfHiQN2_.js` as of this check) includes the Railway URL, `/api/chat`, `fetch(...)`, and `Accept: text/event-stream`.

## Verification

- Backend test suite: `108 passed, 1 skipped, 2 warnings`
- Optional Postgres checkpoint smoke: passed locally with `STRATUM_TEST_DATABASE_URL`.
- RAG acceptance harness: `20` local golden questions passed with Recall@10 `1.0`, groundedness proxy `1.0`, retrieval p50 `1.77ms` / p95 `2.31ms`, and no-key first-token latency `11.11ms`.
- `/api/chat` SSE now uses the compiled LangGraph runtime for direct escalation, intake, about, and open Q&A. Open Q&A streams the graph-prepared retrieval/source state before LLM tokens, then checkpoints the generated result through the graph `generate` node.
- Escalation handoff copy is notification-status-aware and discretion-safe: it refers to EdStratum's Founding leadership team, does not mention the owner by name, says a summary was sent only when the Resend handoff succeeds, and names James from the Founding leadership team only after delivery succeeds.
- Direct escalation routing now uses phrase-level handoff requests rather than broad single-word triggers, with sentiment/frustration detection taking priority for documented frustration phrases.
- Deployed Phase 4 conversation matrix: `54` live turns passed with contract pass rate `1.0`, expected behavior `1.0`, persona consistency `1.0`, no-hallucination proxy `1.0`, snapshot delivery `1.0`, scripted escalation rate `0.2037`, abandonment proxy `0.0`, and first-token latency p50 `222.79ms` / p95 `406.67ms` / max `573.5ms`.
- OpenAI-compatible provider streaming path: covered by parser and progressive-stream contract tests.
- Docker build: passed with the Railway-compatible `${PORT:-8000}` command.
- Secret/token scan: no matches in tracked backend source.
- Live backend SSE smoke test: passed for open/about/escalation paths.
- Live non-eval Resend escalation smoke: passed; the production SSE response
  confirmed a leadership-team summary was sent and completed with
  `DONE escalate=explicit`.
- Live eval-suppressed escalation smoke: passed; response used Founding
  leadership team copy, omitted James until delivery, and omitted calendar links.
- Live progressive streaming spot check: graph-backed open Q&A emitted `searching`, `retrieving`, `composing`, `source`, then tokens; first SSE event in `102.36ms`.
- Live CORS preflight from `https://edstratumlabs.ai`: passed.
- Live frontend SEO tags: meta description, canonical, OG title, and OG description present.
- Live static files: `/robots.txt`, `/sitemap.xml`, `/og-image.png`, `/_headers`, and `/_redirects` all return HTTP 200.

## Known Scope Notes

- LangGraph routing exposes the executable spec topology: `route`, `open`,
  `intake`, `assess`, `about`, `escalation`, `notify`, and shared terminal
  `generate`; PostgresSaver checkpoint support is implemented and production
  runtime verification confirms `checkpointer=postgres`.
- The diagram-only `rag`, `persona`, and `handoff` labels are consolidated into
  branch handlers, matching the spec's executable edge sample while preserving
  open-mode retrieval, persona/about, escalation, SSE streaming, and
  checkpointing behavior.
- Retrieval now uses `rank_bm25`, Chroma-backed dense retrieval, RRF-style fusion, and OpenAI embeddings in production; no-key local/demo runs use deterministic hash embeddings.
- Reranking auto-selects Cohere cross-encoder reranking when `COHERE_API_KEY` is present; the demo Railway env skips Cohere and uses heuristic reranking as allowed by the deploy directive.
- Acceptance metrics run locally through `scripts/eval_rag.py` and against
  Railway through `scripts/eval_deployed_conversations.py`; passive production
  traffic analytics for real visitor escalation and abandonment are not
  instrumented in this demo build.

## Notes

- Railway CLI agent support and the `use-railway` skill are installed and up to date. The official local MCP is configured; OAuth login is required for `railway agent`.
- Custom Railway MCP is configured in Codex as `railway-mcp` with bearer auth via `RAILWAY_CUSTOM_MCP_BEARER_TOKEN`; direct MCP verification returned server `railway_mcp` version `1.28.1` and all `9` tools.
- Cloudflare credentials remain only in the sensitive handoff attachment and were not committed to this repository.

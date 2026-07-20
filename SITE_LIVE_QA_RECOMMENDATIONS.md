# STRATUM Live QA And Recommendations

Checked: 2026-07-20 UTC

## Current Source Map

- Backend source: `/home/z121532/edstratum-v2/stratum_backend`
- Frontend source: `/home/z121532/edstratum-v2/edstratum-v2-frontend`
- Frontend GitHub repo: `https://github.com/theonlygeranium/edstratum-v2-frontend`
- Frontend QA report: `/home/z121532/edstratum-v2/edstratum-v2-frontend/SITE_QA_RECOMMENDATIONS.md`

Earlier notes that the frontend source was missing are now superseded. The source was recovered, patched, committed, pushed, and redeployed from the frontend repo.

## Current Production State

- Site: `https://edstratumlabs.ai`
- Cloudflare Pages project: `edstratumlabs`
- Cloudflare source: GitHub repo `theonlygeranium/edstratum-v2-frontend`
- Latest frontend production code commit verified: `2f95db5`
- Current production entry asset: `/assets/index-Bg_rGm5t.js`
- Current STRATUM chat asset: `/assets/StratumChat-CXnpkHWz.js`
- Backend: `https://stratum-backend-production-a340.up.railway.app`
- Latest backend main commit verified by public health/SSE behavior: `ad1593b`
- Backend runtime previously verified: Writer/Palmyra generation, hash embeddings, Railway Postgres-backed graph/session state

## QA Summary

- Backend health, runtime, pytest suite, RAG eval, and deployed conversation matrix passed in the backend live QA pass.
- Frontend source build passes `npm run build`.
- Local frontend production preview passed desktop and mobile chatbot open/respond checks in mock mode.
- Live production domain loads the source-built frontend entrypoint.
- Live STRATUM chat reached Railway `/api/chat` with HTTP 200 from the production origin.
- Source, built output, and live index scan clean for personal-name, direct-person CTA, and scheduling-link copy.
- Live completed response used discretion-safe leadership handoff language.
- RAG citation enhancement deployed:
  - Public `/api/health` returns `rag: { status: "ok", vectorStoreConnected: true }`.
  - Live `/api/chat` SSE smoke with `X-Stratum-Eval: true` returned HTTP 200, SSE content type, terminal `done`, and citation rows.
  - Live `https://edstratumlabs.ai` rendered and expanded citation excerpts from the production backend.
- Escalation email safety enhancement deployed:
  - Public `/api/escalate` with `X-Stratum-QA: true` returned `{ success: true, status: "suppressed", messageId: "qa-suppressed" }`.
  - Public `/api/chat` with `X-Stratum-Eval: true` returned terminal `done.escalation.status: "suppressed"` for an explicit escalation prompt.
  - Live frontend rendered success/failure confirmations using intercepted SSE only, so no live handoff email was sent.
- Cloudflare Pages Functions middleware deployed:
  - Live `https://edstratumlabs.ai/api/config` returned safe non-secret runtime defaults.
  - Live `https://edstratumlabs.ai/api/health` proxied Railway `/api/health` and returned healthy RAG status.
  - KV namespaces remain unbound until Cloudflare credentials are available, so rate limiting is currently skipped by design.

## Notes For Future Agents

- Use the frontend repo for all future site/chat changes. Do not patch Cloudflare bundle artifacts unless source is unavailable and the fix is urgent.
- The chatbot frontend is under `src/stratum/` in the frontend repo.
- The production backend URL is supplied through `VITE_STRATUM_API_URL`.
- Omitting `VITE_STRATUM_API_URL` locally enables mock mode and avoids sending live handoff notifications.
- Production CORS allows the production domain; localhost requests to Railway are expected to fail unless backend CORS is expanded for a local backend or staging origin.
- Cloudflare Pages is connected to the frontend GitHub repo.
- Pushing frontend `main` automatically deploys production; pushing frontend feature branches creates preview deployments.
- Production frontend currently reaches Railway through the source fallback if `VITE_STRATUM_API_URL` is missing at build time. Preview env vars were last verified as unset, so branch previews may use mock chat unless the backend URL is added to preview settings.
- Frontend commit `371f634` also includes a production-host fallback to the public Railway backend if Cloudflare Pages production builds without `VITE_STRATUM_API_URL`; localhost and branch previews remain mock-mode by default.
- Frontend commit `2f95db5` adds Cloudflare Pages Functions under `functions/`; `/api/health` proxies Railway `/api/health`, `/api/config` returns non-secret feature flags, and `_middleware.ts` applies best-effort KV rate limiting when `RATE_LIMIT` is bound.

## Completed Feature 1

- Enhancement spec Feature 1 citation delta is deployed on the Python/FastAPI backend: `RagCitation`, `citations` SSE events before terminal `done`, citation extraction from retrieved KB chunks, graph checkpoint preservation, and RAG health in `/api/health`.
- Local and production QA passed on 2026-07-20. Railway CLI auth was unavailable in the shell, so public health/runtime/SSE endpoints were used as deployment evidence.

## Completed Feature 2

- Enhancement spec Feature 2 is deployed on the Python/FastAPI backend: structured `EscalationDelivery`, delivery metadata on terminal `done` SSE events, branded Resend HTML plus plaintext payloads, safe `/api/escalate`, session-scoped rate limiting, env aliases `ESCALATION_EMAIL_TO` / `ESCALATION_EMAIL_FROM`, and QA suppression for `X-Stratum-QA` and `X-Stratum-Eval`.
- Local and production QA passed on 2026-07-20. Railway CLI auth was unavailable in the shell, so public health/runtime/SSE endpoints were used as deployment evidence.

## Completed Feature 3

- Enhancement spec Feature 3 is deployed on the frontend Cloudflare Pages project: typed Pages Functions, `/api/health` proxy, `/api/config` runtime flags, best-effort KV rate limiting, and handler tests.
- Local, preview, and production QA passed on 2026-07-20. Wrangler was not authenticated, so KV namespace creation and dashboard binding remain pending.

## Recommended Next Steps

1. Add/verify Cloudflare preview env var `VITE_STRATUM_API_URL` if preview branches should exercise the live backend instead of mock chat.
2. Keep frontend Playwright tests for homepage render, chatbot open, prompt submit, mobile layout, and discretion-safe copy.
3. Keep using `X-Stratum-QA` or `X-Stratum-Eval` for any future live escalation QA unless the user explicitly requests an email test.
4. Create and bind Cloudflare KV namespaces `STRATUM_CONFIG` and `RATE_LIMIT` once credentials are available.
5. Add CI for `npm ci`, `npm run build`, and forbidden-copy scans.
6. Add a small public build manifest with git SHA, build timestamp, backend URL, and asset hashes for easier live verification.
7. Prefer scoped Cloudflare deploy tokens over global credentials, and keep deploy credentials out of checked-in files.
8. Add privacy-safe chatbot funnel analytics for open, first message, readiness completion, backend error, and handoff intent events.

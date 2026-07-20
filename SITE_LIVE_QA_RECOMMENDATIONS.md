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
- Latest frontend production code commit verified: `87c4d5d`
- Current production entry asset: `/assets/index-CntR1RBA.js`
- Current STRATUM chat asset: `/assets/StratumChat-CKo-w4OW.js`
- Backend: `https://stratum-backend-production-a340.up.railway.app`
- Latest backend main commit verified by public health/SSE behavior: `3272b67`
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
- Sentiment escalation enhancement deployed:
  - Local backend pytest passed with `119 passed, 1 skipped`.
  - Live `/api/chat` with `X-Stratum-Eval: true`, `escalationTrigger: "sentiment"`, and `sentimentSignal: "urgency"` returned terminal `done.escalate: "sentiment"` and `done.escalation.status: "suppressed"`.
  - Live frontend rendered urgency handoff UI through intercepted SSE only, so no live handoff email was sent.
- D1 persistence scaffolding deployed:
  - Live `https://edstratumlabs.ai/api/config` returns `persistenceEnabled: false`.
  - Live `POST https://edstratumlabs.ai/api/sessions` returns `503` with `d1_not_configured` until D1 is bound.
  - Live rendered chat smoke verified no `/api/sessions` requests are made while persistence is disabled.

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
- Frontend commit `87c4d5d` adds D1 session persistence scaffolding under `functions/api/sessions/`, plus `schema.sql`; persistence remains inactive until `STRATUM_DB`, `SESSION_SECRET`, schema execution, and KV runtime `persistenceEnabled: true` are configured.
- Backend commit `3272b67` accepts optional `escalationTrigger` and `sentimentSignal` on `/api/chat` requests, preserves them through the graph state, and records `sentiment_signal` in non-secret escalation key signals.

## Completed Feature 1

- Enhancement spec Feature 1 citation delta is deployed on the Python/FastAPI backend: `RagCitation`, `citations` SSE events before terminal `done`, citation extraction from retrieved KB chunks, graph checkpoint preservation, and RAG health in `/api/health`.
- Local and production QA passed on 2026-07-20. Railway CLI auth was unavailable in the shell, so public health/runtime/SSE endpoints were used as deployment evidence.

## Completed Feature 2

- Enhancement spec Feature 2 is deployed on the Python/FastAPI backend: structured `EscalationDelivery`, delivery metadata on terminal `done` SSE events, branded Resend HTML plus plaintext payloads, safe `/api/escalate`, session-scoped rate limiting, env aliases `ESCALATION_EMAIL_TO` / `ESCALATION_EMAIL_FROM`, and QA suppression for `X-Stratum-QA` and `X-Stratum-Eval`.
- Local and production QA passed on 2026-07-20. Railway CLI auth was unavailable in the shell, so public health/runtime/SSE endpoints were used as deployment evidence.

## Completed Feature 3

- Enhancement spec Feature 3 is deployed on the frontend Cloudflare Pages project: typed Pages Functions, `/api/health` proxy, `/api/config` runtime flags, best-effort KV rate limiting, and handler tests.
- Local, preview, and production QA passed on 2026-07-20. Wrangler was not authenticated, so KV namespace creation and dashboard binding remain pending.

## Completed Feature 4

- Enhancement spec Feature 4 is deployed across frontend and backend: frontend sentiment detection with frustration CTA and urgency auto-handoff, backend request metadata for `escalationTrigger` / `sentimentSignal`, and non-secret escalation payload logging of `sentiment_signal`.
- Backend commit `3272b67` is pushed to `main`; frontend commit `3372b43` is pushed to `main` and loaded in production as `/assets/StratumChat-9GA-qGlc.js`.
- Local QA passed on 2026-07-20: frontend `npm run lint`, `npm run build`, `npm test -- tests/sentiment.spec.ts --reporter=list` (`10 passed`), frontend `npm test -- --reporter=list` (`64 passed`), backend `pytest` (`119 passed, 1 skipped`), and backend focused contract tests (`43 passed, 1 skipped`).
- Production QA passed on 2026-07-20 using safe paths only: backend `X-Stratum-Eval: true` returned suppressed sentiment escalation, and frontend rendered urgency handoff with intercepted SSE so no live notification was sent.

## Completed Feature 5

- Enhancement spec Feature 5 is deployed on the frontend Cloudflare Pages project: D1 schema, typed session Function route, edge-signed scoped session tokens, local persistence helper, refresh hydration, and best-effort message/flag sync gated by `persistenceEnabled`.
- Frontend commit `87c4d5d` is pushed to `main` and loaded in production as `/assets/StratumChat-CKo-w4OW.js`; backend code was not changed for this feature.
- Local QA passed on 2026-07-20: frontend `npm run lint`, `npm run build`, `npx wrangler pages functions build`, focused Function tests (`22 passed`), persistence browser tests (`10 passed`), and full frontend suite (`84 passed`).
- Production QA passed on 2026-07-20: `/api/config` returns `persistenceEnabled: false`, `/api/sessions` fails closed with `d1_not_configured`, and live rendered chat makes no session endpoint calls while persistence is disabled.

## Recommended Next Steps

1. Add/verify Cloudflare preview env var `VITE_STRATUM_API_URL` if preview branches should exercise the live backend instead of mock chat.
2. Keep frontend Playwright tests for homepage render, chatbot open, prompt submit, mobile layout, and discretion-safe copy.
3. Keep using `X-Stratum-QA` or `X-Stratum-Eval` for any future live escalation QA unless the user explicitly requests an email test.
4. Create and bind Cloudflare KV namespaces `STRATUM_CONFIG` and `RATE_LIMIT` once credentials are available.
5. Create D1 database `stratum-conversations`, run `schema.sql`, bind it as `STRATUM_DB`, add `SESSION_SECRET`, then set KV runtime `persistenceEnabled: true` only after a live smoke plan is ready.
6. Add CI for `npm ci`, `npm run build`, and forbidden-copy scans.
7. Add a small public build manifest with git SHA, build timestamp, backend URL, and asset hashes for easier live verification.
8. Prefer scoped Cloudflare deploy tokens over global credentials, and keep deploy credentials out of checked-in files.
9. Add privacy-safe chatbot funnel analytics for open, first message, readiness completion, backend error, and handoff intent events.

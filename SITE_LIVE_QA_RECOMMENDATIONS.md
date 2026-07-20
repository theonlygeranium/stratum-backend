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
- Latest source commit observed in Pages production metadata: `ec95e8b`
- Current production entry asset: `/assets/index-BmMnKl08.js`
- Current STRATUM chat asset: `/assets/StratumChat-DcniEbxZ.js`
- Backend: `https://stratum-backend-production-a340.up.railway.app`
- Latest backend main commit verified by public health/SSE behavior: `cde0dbe`
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

## Notes For Future Agents

- Use the frontend repo for all future site/chat changes. Do not patch Cloudflare bundle artifacts unless source is unavailable and the fix is urgent.
- The chatbot frontend is under `src/stratum/` in the frontend repo.
- The production backend URL is supplied through `VITE_STRATUM_API_URL`.
- Omitting `VITE_STRATUM_API_URL` locally enables mock mode and avoids sending live handoff notifications.
- Production CORS allows the production domain; localhost requests to Railway are expected to fail unless backend CORS is expanded for a local backend or staging origin.
- Cloudflare Pages is connected to the frontend GitHub repo.
- Pushing frontend `main` automatically deploys production; pushing frontend feature branches creates preview deployments.
- Production Cloudflare env includes `VITE_STRATUM_API_URL`. Preview env vars were last verified as unset, so branch previews may use mock chat unless the backend URL is added to preview settings.

## Completed Feature 1

- Enhancement spec Feature 1 citation delta is deployed on the Python/FastAPI backend: `RagCitation`, `citations` SSE events before terminal `done`, citation extraction from retrieved KB chunks, graph checkpoint preservation, and RAG health in `/api/health`.
- Local and production QA passed on 2026-07-20. Railway CLI auth was unavailable in the shell, so public health/runtime/SSE endpoints were used as deployment evidence.

## Feature 2 Branch Status

- Branch `feat/escalation-email` adds structured escalation delivery metadata, branded Resend HTML plus plaintext payloads, safe `/api/escalate`, session-scoped rate limiting, env aliases `ESCALATION_EMAIL_TO` / `ESCALATION_EMAIL_FROM`, and QA suppression for `X-Stratum-QA` and `X-Stratum-Eval`.
- Local branch QA passed on 2026-07-20: `./.venv/bin/pytest -q` (`116 passed, 1 skipped`).
- Pending post-merge checks: public `/api/escalate` with `X-Stratum-QA: true`, public `/api/chat` escalation path with `X-Stratum-Eval: true`, and live frontend confirmation UI through a suppressed or mock path only.

## Recommended Next Steps

1. Add/verify Cloudflare preview env var `VITE_STRATUM_API_URL` if preview branches should exercise the live backend instead of mock chat.
2. Keep frontend Playwright tests for homepage render, chatbot open, prompt submit, mobile layout, and discretion-safe copy.
3. Merge and deploy Feature 2, then verify the suppression path before any live escalation QA that could otherwise send email.
4. Add CI for `npm ci`, `npm run build`, and forbidden-copy scans.
5. Add a small public build manifest with git SHA, build timestamp, backend URL, and asset hashes for easier live verification.
6. Prefer scoped Cloudflare deploy tokens over global credentials, and keep deploy credentials out of checked-in files.
7. Add privacy-safe chatbot funnel analytics for open, first message, readiness completion, backend error, and handoff intent events.

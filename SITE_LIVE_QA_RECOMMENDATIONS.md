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
- Latest source commit deployed through Pages metadata: `366e4c8`
- Current production entry asset: `/assets/index-BChwigZm.js`
- Current STRATUM chat asset: `/assets/StratumChat-Cl3e2M0J.js`
- Backend: `https://stratum-backend-production-a340.up.railway.app`
- Backend runtime previously verified: Writer/Palmyra generation, hash embeddings, Railway Postgres-backed graph/session state

## QA Summary

- Backend health, runtime, pytest suite, RAG eval, and deployed conversation matrix passed in the backend live QA pass.
- Frontend source build passes `npm run build`.
- Local frontend production preview passed desktop and mobile chatbot open/respond checks in mock mode.
- Live production domain loads the source-built frontend entrypoint.
- Live STRATUM chat reached Railway `/api/chat` with HTTP 200 from the production origin.
- Source, built output, and live index scan clean for personal-name, direct-person CTA, and scheduling-link copy.
- Live completed response used discretion-safe leadership handoff language.

## Notes For Future Agents

- Use the frontend repo for all future site/chat changes. Do not patch Cloudflare bundle artifacts unless source is unavailable and the fix is urgent.
- The chatbot frontend is under `src/stratum/` in the frontend repo.
- The production backend URL is supplied through `VITE_STRATUM_API_URL`.
- Omitting `VITE_STRATUM_API_URL` locally enables mock mode and avoids sending live handoff notifications.
- Production CORS allows the production domain; localhost requests to Railway are expected to fail unless backend CORS is expanded for a local backend or staging origin.
- Cloudflare Pages is still deployed by direct Wrangler upload. Connecting the private GitHub repo to Cloudflare Pages remains recommended.

## Recommended Next Steps

1. Connect Cloudflare Pages to the private GitHub frontend repo so `main` can deploy automatically from source.
2. Add frontend Playwright tests for homepage render, chatbot open, prompt submit, mobile layout, and discretion-safe copy.
3. Add a staging or eval-only backend path for escalation QA that cannot send live notifications.
4. Add CI for `npm ci`, `npm run build`, and forbidden-copy scans.
5. Add a small public build manifest with git SHA, build timestamp, backend URL, and asset hashes for easier live verification.
6. Prefer scoped Cloudflare deploy tokens over global credentials, and keep deploy credentials out of checked-in files.
7. Add privacy-safe chatbot funnel analytics for open, first message, readiness completion, backend error, and handoff intent events.

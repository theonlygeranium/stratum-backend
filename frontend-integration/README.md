# STRATUM Frontend Integration Status

The original Phase 1 patch note in this directory is superseded. The frontend source now lives at `/home/z121532/edstratum-v2/edstratum-v2-frontend`, and the STRATUM chat already includes the backend SSE adapter under `src/stratum/stratumApi.ts`.

Current behavior:

- Production `edstratumlabs.ai` and `www.edstratumlabs.ai` use the Railway backend URL from `VITE_STRATUM_API_URL`, with a production-host fallback to `https://stratum-backend-production-a340.up.railway.app`.
- Local development and Cloudflare preview branches use mock mode when `VITE_STRATUM_API_URL` is unset, which is the safe default for UI QA because it cannot send live handoff emails.
- Same-origin Cloudflare Pages Functions proxy `/api/health`, `/api/config`, `/api/escalate`, `/api/tts`, and D1-backed `/api/sessions` routes when the corresponding bindings and runtime flags are configured.
- Public deployment metadata is available at `/build-manifest.json` and should be the first live verification check after each frontend production deploy.

Do not reapply the old integration patch. Future frontend changes belong in the frontend repo source, followed by `npm run type-check`, `npm run lint`, `npm run build`, `npx wrangler pages functions build`, focused Playwright coverage, hosted `CI / build-and-test`, and live manifest or rendered QA as appropriate.

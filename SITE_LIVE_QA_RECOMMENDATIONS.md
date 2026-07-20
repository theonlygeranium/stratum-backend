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
- Latest frontend production code-bearing commit verified: `36f201f`
- Latest verified code-bearing frontend manifest commit: `36f201f`; docs-only pushes can advance the manifest git SHA while leaving code-bearing asset hashes unchanged.
- Latest verified frontend workflow-only manifest commit: `d01ce68`
- Current production entry asset: `/assets/index-Cld5-OrE.js`
- Current production stylesheet asset: `/assets/index-DH0EGGDC.css`
- Current STRATUM chat asset: `/assets/StratumChat-5iN0axbq.js`
- Current PDF snapshot assets: `/assets/stratumPDF-Bgc_chGe.js`, `/assets/pdf-vendor-B7fMFYQc.js`
- Current public build manifest: `https://edstratumlabs.ai/build-manifest.json`
- Backend: `https://stratum-backend-production-a340.up.railway.app`
- Latest backend code/helper commit pushed: `728f217`
- Latest backend workflow-only commit pushed: `f7dced4`
- Public backend health/runtime routes remain healthy after the source pushes; GitHub status for `f7dced4` reports Railway deployment success plus `Backend CI / pytest-and-rag` success.
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
- Voice/TTS scaffolding deployed:
  - Live `https://edstratumlabs.ai/api/config` returns `voiceEnabled: false`.
  - Live `https://edstratumlabs.ai/api/health` returns `tts: { status: "unconfigured", provider: "elevenlabs" }`.
  - Live backend `/api/tts` enforces the 500-character request contract; validation-only QA returned HTTP 422 without invoking the provider.
  - Live rendered chat smoke verified zero voice playback or mic controls appear while the runtime flag remains disabled.
- PDF snapshot download deployed:
  - Live production loads frontend code-bearing commit `3904989` through `/assets/index-BQPzEWy3.js` and `/assets/StratumChat-Dc9NE68U.js`.
  - The chat chunk lazy-loads `/assets/stratumPDF-Bgc_chGe.js` and `/assets/pdf-vendor-B7fMFYQc.js`.
  - Live rendered smoke intercepted `/api/chat`, reached an escalation state, showed `Download Summary`, generated an `edstratum-intake-...pdf` download, and produced no console errors or live notification traffic.
- SOT QA gate update:
  - Backend source commit `9172431` aligns the direct `/api/escalate` failure contract with the spec, updates the branded subject line, and switches deploy docs to `ESCALATION_EMAIL_TO` / `ESCALATION_EMAIL_FROM`.
  - Local backend pytest passed with `123 passed, 1 skipped`.
  - Direct Railway `/api/escalate` with `X-Stratum-QA: true` and a complete payload returned `{ "success": true, "status": "suppressed" }`, so no notification provider call was made.
  - The production failure path was not exercised because production has notifications configured and a non-QA test could send a real handoff email.
  - Frontend commit `17124c1` was previously deployed with main CI `29728690249` passing `112` Playwright tests, and rendered production smoke verified intercepted handoff UI, PDF download generation, hidden voice controls while disabled, and no console/page errors.
- Same-origin proxy and TTS streaming update:
  - Frontend commit `e1ff6d6` adds Cloudflare Pages Functions for `/api/escalate` and `/api/tts`, switches browser TTS playback to same-origin `/api/tts`, and passed main CI `29729914138` with `120 passed`.
  - Production `https://edstratumlabs.ai/api/escalate` with `X-Stratum-QA: true` returned `200` and `status: "suppressed"` without a live notification.
  - Production `https://edstratumlabs.ai/api/tts` returned Railway validation `422` for an invalid payload and `503 tts_not_configured` for a valid validation-only payload, confirming the same-origin proxy reaches Railway without invoking ElevenLabs.
  - Backend source commit `bfb1987` streams ElevenLabs provider bytes through FastAPI `StreamingResponse`; local backend pytest passed with `123 passed, 1 skipped`.
- Browser TTS playback update:
  - Frontend commit `3904989` streams successful `/api/tts` responses through MediaSource/Web Audio when supported and retains buffered `arrayBuffer()` decode playback as a fallback.
  - Local frontend QA passed on 2026-07-20: `npm run type-check`, `npm run lint`, `npm run build`, `npx wrangler pages functions build`, focused voice browser tests (`16 passed`), and full Playwright suite (`122 passed`).
  - Hosted main CI `29731627328` passed with `122 passed`, Cloudflare Pages deployed `/assets/index-BQPzEWy3.js` and `/assets/StratumChat-Dc9NE68U.js`, live `/api/config` still returns `voiceEnabled: false`, and rendered production smoke verified zero voice controls plus zero TTS requests while disabled.
- Public build manifest update:
  - Frontend commit `c5f6431` adds `/build-manifest.json` generation after `vite build`, a short-lived Cloudflare cache header, a CI dist assertion, and Playwright coverage for the manifest contract.
  - Local frontend QA passed on 2026-07-20: `npm run type-check`, `npm run lint`, `npm run build`, `npx wrangler pages functions build`, focused STRATUM browser tests (`28 passed`), and full Playwright suite (`124 passed`).
  - Hosted main CI `29733457960` passed with `124 passed`, Cloudflare Pages production succeeded, and live `/build-manifest.json` returned HTTP 200 with backend URL `https://stratum-backend-production-a340.up.railway.app`, 13 assets, and a matching live chat-asset SHA-256 hash. Docs-only frontend pushes can advance the manifest git SHA while leaving the code-bearing asset hashes unchanged.
- Frontend QA suppression and CI gate update:
  - Frontend commit `43ce52e` adds a preview/staging-only `VITE_STRATUM_QA=true` build gate that sends `X-Stratum-QA: true` on real-backend chat requests, updates `deploy.sh` to emergency direct-upload only, and adds `npx wrangler pages functions build` to hosted CI.
  - Local frontend QA passed on 2026-07-20: `npm run type-check`, `npm run lint`, a QA build proving `X-Stratum-QA` is emitted only when `VITE_STRATUM_QA=true`, a normal production build, `npx wrangler pages functions build`, focused escalation/sentiment tests (`16 passed`), and the full Playwright suite (`124 passed`).
  - Hosted main CI `29735401007` passed with `124 passed`, Cloudflare Pages production succeeded, and live `/build-manifest.json` returned commit `43ce52e`, entry asset `/assets/index-DGGaBcY3.js`, chat asset `/assets/StratumChat-Dr5FwyGc.js`, 13 assets, and a matching live chat-asset SHA-256 hash. The production chat asset does not contain `X-Stratum-QA`.
- Frontend voice and persistence readiness update:
  - Frontend commit `a2a9551` adds D1 session deletion, admin retention purge, reset-time persisted-session deletion, `idx_sessions_last_active`, same-origin microphone policy, and same-origin `/api/tts` fail-closed behavior unless runtime `voiceEnabled` is true.
  - Local frontend QA passed on 2026-07-20: `npm run type-check`, `npm run lint`, `npm run build`, `npx wrangler pages functions build`, focused Functions tests (`42 passed`), focused persistence tests (`12 passed`), focused voice tests (`16 passed`), and full Playwright with one worker (`138 passed`).
  - Hosted main CI `29736780944` passed with `138 passed`, Cloudflare Pages production succeeded, and live `/build-manifest.json` returned commit `a2a9551`, entry asset `/assets/index-y7cgbAE2.js`, chat asset `/assets/StratumChat-YqNBO1Mg.js`, 13 assets, and `Cache-Control: public, max-age=60, must-revalidate`. Live root headers include `Permissions-Policy: camera=(), microphone=(self), geolocation=(), payment=()`, and live `/api/tts` returns `503` with `detail: "tts_disabled"` while `/api/config` returns `voiceEnabled: false`.
- Frontend privacy-safe analytics update:
  - Frontend commit `36f201f` adds typed and property-whitelisted STRATUM analytics events for chat open, first message, readiness completion, backend error, and handoff intent; a same-origin `/api/analytics` Pages Function that stores aggregate daily counters only when `ANALYTICS_EVENTS` is bound; and browser/Functions tests proving prompt text, intake answers, raw session IDs, and unsafe properties are not stored.
  - Local frontend QA passed on 2026-07-20: `npm run type-check`, `npm run lint`, `npm run build`, `npx wrangler pages functions build`, focused analytics Functions tests (`10 passed`), focused analytics browser tests (`8 passed`), and full Playwright with one worker (`156 passed`).
  - Hosted main CI `29738422278` passed with `156 passed`, Cloudflare Pages production succeeded, and live `/build-manifest.json` returned commit `36f201f`, entry asset `/assets/index-Cld5-OrE.js`, chat asset `/assets/StratumChat-5iN0axbq.js`, 13 assets, and `Cache-Control: public, max-age=60, must-revalidate`. Live `/api/analytics` currently returns `503` with `error: "analytics_not_configured"` and `Cache-Control: no-store` because the analytics KV binding is not active.
- RAG provider path update:
  - Backend commit `41b2ae9` adds modeled Pinecone settings, OpenAI/Pinecone provider plumbing through `StratumAgent` and `HybridRetriever`, direct Pinecone upsert/query support in `DenseVectorIndex`, Chroma/memory fallback on setup or query failure, and eval harness provider configuration.
  - Local backend QA passed on 2026-07-20: focused config/vector/RAG/runtime tests (`65 passed, 1 skipped`), full pytest (`129 passed, 1 skipped`), RAG eval (`passed: true`, recall@10 `1.0`, groundedness proxy `1.0`), and `pip install --dry-run -r requirements.txt` resolved `pinecone-7.3.0`.
  - Public Railway `/api/health` and `/api/runtime` remained healthy after the push. Runtime still reports `embedding_provider: "hash"` and `vector_store_provider: "chroma"` because production has not enabled the managed provider envs.
- Backend CI update:
  - Backend commit `81d59bb` adds GitHub Actions workflow `Backend CI` with Python 3.11 dependency install, full `pytest -q`, `scripts/eval_rag.py --json`, and custom commit status `Backend CI / pytest-and-rag`.
  - Hosted run `29732894534` passed on 2026-07-20; commit status `Backend CI / pytest-and-rag` returned `success`, and Railway posted a successful deployment status for `stratum-backend-production-a340.up.railway.app`.
  - Safe public post-push smoke passed: direct Railway `/api/health`, direct Railway `/api/runtime`, and Cloudflare same-origin `/api/health` all returned healthy responses. Runtime still reports `hash`/`chroma` until managed RAG env activation.
  - Backend commit `3d6387a` hardens the RAG eval step with Bash `pipefail` and uploads `rag-eval-report.json` on every hosted run. Hosted run `29733841811` passed in 49 seconds, Railway deployment status returned `success`, and safe public post-push health/runtime smoke remained healthy.
- Backend deployment readiness cleanup:
  - Backend commit `e308070` refreshes deployment docs and readiness checks around current Writer/Resend/Railway/Cloudflare env names, sibling frontend repo paths, public build-manifest verification, and the live runtime state where managed OpenAI/Pinecone and ElevenLabs remain inactive.
  - Backend commit `728f217` aligns Railway and Cloudflare helper scripts with the current runtime: Writer and primary escalation envs are required, managed RAG/TTS envs are optional with provider guardrails, frontend helper defaults point at the sibling source repo, and `eval_rag.py` clears external API keys for the no-key evaluation path.
  - Local backend QA passed on 2026-07-20: shell syntax checks for deploy helpers, `git diff --check`, dry-run Cloudflare env helper, live SEO/build-manifest verification, full pytest (`129 passed, 1 skipped`), and RAG eval (`passed: true`, recall@10 `1.0`, groundedness proxy `1.0`) using `hash`/`chroma`/`heuristic`.
  - Hosted backend CI runs `29734912402` and `29735038155` passed, Railway deployment status for `728f217` returned `success`, and safe public health/runtime smoke remained healthy.
- GitHub Actions Node 24 migration update:
  - Frontend commit `d01ce68` updates CI action pins to `actions/checkout@v5`, `actions/setup-node@v5`, `actions/upload-artifact@v6`, and `actions/github-script@v8` while leaving the frontend app build runtime at `node-version: '20'`. Hosted main CI `29739390956` passed with `156 passed`; strict log search found no deprecated Node.js 20 JavaScript-action warning. Live `/build-manifest.json` returned commit `d01ce68` with unchanged code-bearing assets `/assets/index-Cld5-OrE.js`, `/assets/index-DH0EGGDC.css`, and `/assets/StratumChat-5iN0axbq.js`.
  - Backend commit `f7dced4` updates CI action pins to `actions/checkout@v5`, `actions/setup-python@v6`, `actions/upload-artifact@v6`, and `actions/github-script@v8` while leaving the backend Python runtime at `3.11`. Hosted backend CI run `29739391077` passed, GitHub status for `f7dced4` is `success`, Railway deployment status is `success`, and public Railway `/api/health` plus `/api/runtime` remained healthy.

## Notes For Future Agents

- Use the frontend repo for all future site/chat changes. Do not patch Cloudflare bundle artifacts unless source is unavailable and the fix is urgent.
- The chatbot frontend is under `src/stratum/` in the frontend repo.
- The production backend URL is supplied through `VITE_STRATUM_API_URL`.
- Omitting `VITE_STRATUM_API_URL` locally enables mock mode and avoids sending live handoff notifications.
- Production CORS allows the production domain and `http://localhost:5173`; other local or preview origins need explicit expansion.
- Cloudflare Pages is connected to the frontend GitHub repo.
- Pushing frontend `main` automatically deploys production; pushing frontend feature branches creates preview deployments.
- Production frontend currently reaches Railway through the source fallback if `VITE_STRATUM_API_URL` is missing at build time. Preview env vars were last verified as unset, so branch previews may use mock chat unless the backend URL is added to preview settings.
- Frontend commit `371f634` also includes a production-host fallback to the public Railway backend if Cloudflare Pages production builds without `VITE_STRATUM_API_URL`; localhost and branch previews remain mock-mode by default.
- Frontend commit `2f95db5` adds Cloudflare Pages Functions under `functions/`; `/api/health` proxies Railway `/api/health`, `/api/config` returns non-secret feature flags, and `_middleware.ts` applies best-effort KV rate limiting when `RATE_LIMIT` is bound.
- Frontend commit `87c4d5d` adds D1 session persistence scaffolding under `functions/api/sessions/`, plus `schema.sql`; persistence remains inactive until `STRATUM_DB`, `SESSION_SECRET`, schema execution, and KV runtime `persistenceEnabled: true` are configured.
- Backend commit `3272b67` accepts optional `escalationTrigger` and `sentimentSignal` on `/api/chat` requests, preserves them through the graph state, and records `sentiment_signal` in non-secret escalation key signals.
- Backend commit `fdb357a` adds the ElevenLabs TTS proxy contract at `/api/tts` and `/tts`, guarded by Railway-side `ELEVENLABS_API_KEY` and session-scoped rate limiting.
- Frontend commit `e079033` adds voice input and TTS UI, gated by Cloudflare runtime `voiceEnabled` plus build-time `VITE_TTS_ENABLED`.
- Frontend commit `395d0b8` adds client-side PDF session snapshots, lazy-loaded PDF renderer chunks, and download UI after readiness completion or escalation.
- Frontend commit `e1ff6d6` adds same-origin Cloudflare proxy routes for `/api/escalate` and `/api/tts`; backend commit `bfb1987` streams TTS provider bytes instead of buffering the complete provider response first.
- Frontend commit `3904989` streams browser TTS playback through MediaSource where supported, with the buffered decode path retained for unsupported browsers.
- Backend commit `41b2ae9` adds source-ready OpenAI embeddings plus Pinecone vector store plumbing with Chroma/memory fallback and local fake-SDK tests.
- Frontend commit `c5f6431` adds public non-secret deployment metadata at `/build-manifest.json`.
- Backend commit `3d6387a` adds the hosted backend CI gate hardening and keeps custom status context `Backend CI / pytest-and-rag`.
- Frontend commit `43ce52e` adds preview/staging-only `VITE_STRATUM_QA=true` support for `X-Stratum-QA: true`; leave it unset in production.
- Frontend commit `a2a9551` adds D1 deletion/retention purge primitives, same-origin microphone policy readiness, and same-origin `/api/tts` runtime fail-closed behavior.
- Frontend commit `36f201f` adds privacy-safe aggregate chatbot analytics readiness and same-origin `/api/analytics`, gated by the optional Cloudflare KV binding `ANALYTICS_EVENTS`.
- Backend commit `728f217` keeps deploy helpers aligned with current runtime env names and makes optional managed RAG/TTS variables explicit without printing secret values.
- Frontend commit `d01ce68` and backend commit `f7dced4` migrate GitHub Actions to Node 24-native action majors. This does not change the frontend app `node-version: '20'` or backend Python `3.11` runtime choices.

## Current SOT Blockers

- GitHub branch protection for frontend `main` is not configured to require `CI / build-and-test`; this is still a release-governance blocker. A GitHub API attempt on 2026-07-20 returned HTTP 403 requiring GitHub Pro or a public repository before branch protection can be enabled.
- Cloudflare KV rate limiting is not active in production. Live rapid `/api/config` probes did not produce HTTP 429, and the middleware skips enforcement until `RATE_LIMIT` is bound.
- Cloudflare analytics aggregation is not active in production. Live `/api/analytics` returns `503 analytics_not_configured` until `ANALYTICS_EVENTS` is bound.
- Cloudflare D1 conversation persistence is not active. `/api/config` returns `persistenceEnabled: false`, and `/api/sessions/.../messages` returns `503 d1_not_configured`.
- Voice/TTS is not active in production. `/api/config` returns `voiceEnabled: false`, `/api/health` reports `tts.status: "unconfigured"`, and live same-origin `/api/tts` fails closed with `503 tts_disabled` while runtime voice is disabled.
- Backend runtime reports `embedding_provider: "hash"` and `vector_store_provider: "chroma"`; the OpenAI/Pinecone path is now source-ready and locally tested, but production still needs Railway env activation before the managed provider path is live.
- Wrangler and Railway CLI are unauthenticated in this shell, and no safe control-plane tokens are present, so Cloudflare bindings, Railway env vars, and exact deployment SHAs cannot be changed or verified from here.

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

## Completed Feature 6

- Enhancement spec Feature 6 is deployed across frontend and backend: Web Speech API voice input, TTS playback toggle, markdown-stripped TTS payloads, reduced-motion guardrails, same-origin Cloudflare `/api/tts` proxying, browser MediaSource streaming playback with buffered fallback, and a FastAPI ElevenLabs proxy with streaming response, 500-character validation, plus 10-per-session/minute rate limiting.
- Backend commit `fdb357a` is pushed to `main`; frontend commit `e079033` is pushed to `main` and loaded in production as `/assets/StratumChat-CzklqdIB.js`.
- Local QA passed on 2026-07-20: backend pytest (`123 passed, 1 skipped`), backend focused TTS/health/escalation/LLM tests (`9 passed`), frontend `npm run lint`, frontend `npm run build`, `npx wrangler pages functions build`, focused voice/proxy tests (`44 passed`), and full frontend suite (`120 passed`).
- Hosted main CI initially passed on 2026-07-20 with `98 passed`; current frontend main CI for same-origin proxy coverage passed with `120 passed`. Production QA used safe paths only: no live TTS generation, `/api/tts` validation-only checks returned 422/503, `/api/config` leaves `voiceEnabled: false`, and rendered production chat shows no voice controls while disabled.
- Follow-up frontend QA for browser TTS streaming passed with `npm run type-check`, `npm run lint`, `npm run build`, `npx wrangler pages functions build`, focused voice browser tests (`16 passed`), full Playwright suite (`122 passed`), hosted main CI `29731627328` (`122 passed`), and Cloudflare Pages production success for code-bearing commit `3904989`.

## Completed Feature 7

- Enhancement spec Feature 7 is deployed on the frontend Cloudflare Pages project: client-side `@react-pdf/renderer` session summary generation, completion/escalation-gated `Download Summary` UI, no server round-trip for PDF generation, and `tests/pdf-snapshot.spec.ts`.
- Frontend commit `395d0b8` is pushed to `main` and loaded in production as `/assets/StratumChat-DZnOcHe2.js`, with lazy PDF chunks `/assets/stratumPDF-Bgc_chGe.js` and `/assets/pdf-vendor-B7fMFYQc.js`; backend code was not changed for this feature.
- Local QA passed on 2026-07-20: frontend `npm run lint`, frontend `npm run build`, `npx wrangler pages functions build`, no client `fs`/`path`/`crypto` imports, focused PDF tests (`12 passed`), and full frontend suite (`110 passed`).
- Hosted branch and main CI passed on 2026-07-20 with `110 passed`; production QA used safe paths only by intercepting `/api/chat`, verifying the PDF download control and generated PDF without triggering live escalation/email delivery.

## Recommended Next Steps

1. Add/verify Cloudflare preview env var `VITE_STRATUM_API_URL` if preview branches should exercise the live backend instead of mock chat.
2. Keep frontend Playwright tests for homepage render, chatbot open, prompt submit, mobile layout, and discretion-safe copy.
3. Keep using `X-Stratum-QA` or `X-Stratum-Eval` for any future live escalation QA unless the user explicitly requests an email test.
4. Create and bind Cloudflare KV namespaces `STRATUM_CONFIG` and `RATE_LIMIT` once credentials are available.
5. Create D1 database `stratum-conversations`, run `schema.sql`, bind it as `STRATUM_DB`, add `SESSION_SECRET`, choose an operational purge cadence using `/api/sessions/purge`, then set KV runtime `persistenceEnabled: true` only after a live smoke plan is ready.
6. Configure voice/TTS only after a safe rollout plan: set Railway `ELEVENLABS_API_KEY`, optional `ELEVENLABS_VOICE_ID`, Cloudflare Pages `VITE_TTS_ENABLED=true`, then KV runtime `voiceEnabled: true`.
7. Activate managed RAG providers only after staging smoke: set Railway `EMBEDDING_PROVIDER=openai`, `VECTOR_STORE_PROVIDER=pinecone`, `PINECONE_API_KEY`, `PINECONE_INDEX`, optional `PINECONE_NAMESPACE`, then verify `/api/runtime` reports `openai`/`pinecone` and RAG eval remains above threshold.
8. Add branch protection for backend `main` requiring `Backend CI / pytest-and-rag`, and keep frontend `CI / build-and-test` required once GitHub plan controls allow it.
9. Use `/build-manifest.json` as the first frontend deploy verification check before deeper rendered QA.
10. Prefer scoped Cloudflare deploy tokens over global credentials, and keep deploy credentials out of checked-in files.
11. Bind Cloudflare KV namespace `ANALYTICS_EVENTS` to activate the source-ready aggregate chatbot analytics counters, then verify `/api/analytics` returns `202` for an allowlisted test event.
12. Evaluate a separate frontend CI app-runtime move from Node 20 to Node 24, or pin Wrangler to a Node 20-compatible version, because the action-runtime migration did not change the app runtime.

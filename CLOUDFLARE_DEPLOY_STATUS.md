# STRATUM Deploy Status

Checked on 2026-07-20 UTC after frontend asset fallback hardening, backend release-audit expectation update, and production smokes.

## Backend

- GitHub repository: `theonlygeranium/stratum-backend`
- Branch: `main`
- Railway project/environment: `sunny-ambition / production`
- Public backend URL: `https://stratum-backend-production-a340.up.railway.app`
- Latest backend code-bearing commit verified for managed RAG plumbing:
  `41b2ae9`
- Latest backend workflow/action-migration commit verified: `f7dced4`
- Latest backend runtime/tooling commit verified locally, deployed on Railway,
  and live-smoked: `ac6a69a`
- Docs-only commits can advance Railway deployment metadata without changing
  backend runtime behavior. Verify the current deployment through GitHub commit
  status, Railway deployment status, and public `/api/health` plus `/api/runtime`.

Current public runtime evidence:

- `GET /api/health` returns healthy STRATUM status with `backend_enabled: true`,
  RAG `status: "ok"`, `vectorStoreConnected: true`, and TTS
  `status: "unconfigured"` / `provider: "elevenlabs"`.
- `GET /api/runtime` reports `graph_runtime=langgraph`,
  `database_configured=true`, `session_store_backend=postgres`,
  `embedding_provider=hash`, `vector_store_provider=chroma`,
  `reranker_provider=heuristic`, `llm_configured=true`,
  `llm_provider=writer`, `openai_api_key_configured=true`,
  `notifications_configured=true`, `allowed_origins_env_configured=true`, and
  `required_cors_origins_present=true`.
- Managed OpenAI/Pinecone retrieval is source-ready but not active in
  production until Railway sets `EMBEDDING_PROVIDER=openai`,
  `VECTOR_STORE_PROVIDER=pinecone`, `PINECONE_API_KEY`, `PINECONE_INDEX`, and
  optional `PINECONE_NAMESPACE`.
- Voice/TTS is source-ready but inactive until Railway sets
  `ELEVENLABS_API_KEY` and the frontend/Cloudflare runtime flags are enabled.

## Cloudflare Pages

- Pages project: `edstratumlabs`
- Production aliases: `https://edstratumlabs.ai`,
  `https://www.edstratumlabs.ai`
- Frontend GitHub repository: `theonlygeranium/edstratum-v2-frontend`
- Latest frontend production app code/tooling commit verified locally and live:
  `b51a623`
- Latest verified app code-bearing asset commit: `b51a623`; it refreshes the
  entry/chat/service bundle hashes after the Pages fallback fix and confirms
  the seven-question STRATUM intake runtime contract.
- Frontend GitHub Actions action-migration commit verified: `d01ce68`;
  frontend CI app-runtime migration commit verified: `f2c969b`;
  CI Playwright server-ownership fix commit `84e01ce` is contained in current
  frontend `main`; Wrangler pin commit `76b97ba`, live-smoke command commit
  `bb8f3b4`, rendered live-smoke command commit `52cdf47`, asset-smoke
  hardening commit `7eb42dd`, Pages fallback fix commit `b341b07`, and asset
  hash refresh commit `b51a623` are deployed but hosted CI proof is pending
  because GitHub Actions run `29748630950` failed before starting any steps due
  to an account billing/spending-limit blocker.
- Current production metadata endpoint:
  `https://edstratumlabs.ai/build-manifest.json`
- The manifest intentionally exposes only non-secret deployment metadata:
  git SHA, branch, build timestamp, backend URL, hashed asset paths, sizes, and
  SHA-256 hashes. Docs-only frontend pushes can advance the manifest SHA while
  code-bearing asset hashes remain unchanged.
- Production build-time env var `VITE_STRATUM_API_URL` is configured in
  Cloudflare Pages; source also includes a production-host fallback to
  `https://stratum-backend-production-a340.up.railway.app`.
- Preview env vars may omit `VITE_STRATUM_API_URL`, so preview chat can run in
  mock mode unless Cloudflare Preview settings are updated.

## Verification

- Backend hosted CI status context: `Backend CI / pytest-and-rag`
- Frontend hosted CI status context: `CI / build-and-test`
- Backend CI runs `pytest -q`, `scripts/eval_rag.py --json` with Bash
  `pipefail`, and uploads `rag-eval-report.json` every run.
- Backend commit `5793eee` adds `scripts/live_backend_smoke.py` for safe
  deployed API/RAG/runtime smoke: public health, production CORS, runtime
  providers, grounded RAG SSE with citations, and an `X-Stratum-Eval`
  suppressed escalation SSE contract check. Local pytest (`129 passed,
  1 skipped`), RAG eval, pre-deploy live backend smoke, Railway deployment
  success, post-deploy live backend smoke, and frontend same-origin live smoke
  all passed.
- Backend commit `d45f4c9` adds `scripts/live_release_audit.py` for
  non-mutating release governance: GitHub branch protection and checks,
  Cloudflare Pages deployment state, live frontend manifest/runtime flags,
  Railway deployment status, and backend health/runtime. Local py_compile,
  public-only audit, full audit with four expected governance blockers, full
  pytest (`129 passed, 1 skipped`), Railway deployment success, and post-deploy
  backend live smoke all passed. Full audit currently blocks on frontend/backend
  branch protection plus the GitHub Actions billing/spending-limit failures.
- Backend commit `406089f` hardens SOT QA by making the graph SSE no-key path
  fall back to substantive retrieved context when the provider stream is empty,
  keeping confirmed handoff copy name-neutral, and adding answer-substance plus
  citation-support checks to the deployed 54-scenario conversation matrix.
  Local py_compile, focused SSE/conversation tests (`99 passed, 1 skipped`),
  RAG eval, full pytest (`131 passed, 1 skipped`), Railway deployment success,
  post-deploy backend smoke, deployed matrix, and release audit matrix coverage
  passed. Full release audit still blocks only on branch protection plus hosted
  GitHub Actions billing/spending-limit failures.
- Backend commit `ac6a69a` makes release-audit runtime expectations
  configurable through non-secret CLI flags and env vars while preserving the
  current production defaults. Local py_compile, focused release-audit tests
  (`5 passed`), full pytest (`136 passed, 1 skipped`), `git diff --check`, and
  public-only release audit with zero blockers passed. Railway deployment
  status returned success; post-deploy backend smoke passed; release audit with
  `--include-conversation-matrix` confirmed public runtime and the deployed
  54-scenario matrix while still blocking only on branch protection plus hosted
  GitHub Actions billing/spending-limit failures.
- Frontend CI runs type-check, lint, production build, dist manifest assertion,
  pinned Cloudflare Pages Functions build, forbidden-copy scan, and Playwright.
  Latest verified frontend workflow run before the billing blocker was
  `29741097306`, which passed with `156` Playwright tests.
- GitHub Actions are now pinned to Node 24-native action majors in the frontend
  (`d01ce68`) and backend (`f7dced4`) workflows. Strict hosted-log searches
  found no deprecated Node.js 20 JavaScript-action warning after migration.
- Frontend CI now installs Node 24 for the app checks at commit `f2c969b`.
  Hosted run `29741097306` passed with `156` Playwright tests and confirmed
  `node: v24.18.0`; local Node 24 QA also passed type-check, lint, build,
  Wrangler `4.112.0` Pages Functions build, and full Playwright.
- Frontend commit `76b97ba` pins Wrangler as exact devDependency `4.112.0` and
  uses `./node_modules/.bin/wrangler` in CI and `deploy.sh`. Local Node 24 QA
  passed `npm ci`, `bash -n deploy.sh`, the guarded non-deploy helper smoke,
  pinned Wrangler version check, type-check, lint, production build, pinned
  Pages Functions build, and full Playwright (`156 passed`).
- Frontend commit `bb8f3b4` adds `npm run qa:live` for safe production smoke:
  cache-busted manifest commit assertion, runtime config, same-origin health,
  disabled TTS fail-closed behavior, analytics fail-closed behavior while KV is
  unbound, direct Railway health/runtime, and forbidden-copy scans on root HTML
  plus the current STRATUM chat asset. Local and post-deploy smoke passed with
  `EXPECTED_MANIFEST_COMMIT=bb8f3b4`.
- Frontend commit `52cdf47` adds `npm run qa:live:rendered` for production
  browser smoke: page identity, nonblank render, framework-overlay absence,
  console/page/request diagnostics, forbidden-copy scans, desktop STRATUM chat
  open, live non-escalation RAG response with expandable citations, hidden
  voice controls while disabled, mobile dialog bounds, and screenshots under
  `/tmp`. Local checks, Cloudflare Pages deployment, post-deploy `qa:live`, and
  post-deploy `qa:live:rendered` all passed.
- Frontend commits `05d225a`, `7eb42dd`, `b341b07`, and `b51a623` harden the
  seven-question intake contract, live asset MIME checks, Cloudflare Pages
  missing-asset behavior, and current bundle hashes. Local frontend QA through
  `b51a623` passed type-check, lint, production build, pinned Pages Functions
  build, and full Playwright (`162 passed`). Post-deploy
  `EXPECTED_MANIFEST_COMMIT=b51a623 npm run qa:live` and
  `EXPECTED_MANIFEST_COMMIT=b51a623 npm run qa:live:rendered` both passed.
- GitHub Actions run `29748630950` for `b51a623` failed before starting any
  steps because of an account billing/spending-limit blocker; rerun hosted CI
  after billing/settings are corrected.
- Live same-origin `/api/health` on `https://edstratumlabs.ai` proxies Railway
  and returns healthy status.
- Live `/api/config` currently returns `ragEnabled: true`,
  `voiceEnabled: false`, `persistenceEnabled: false`, and
  `maxIntakeQuestions: 7`.
- Live build manifest after the rendered live-smoke deploy returned HTTP 200 with
  `Cache-Control: public, max-age=60, must-revalidate`, commit `b51a623`, the
  Railway backend URL, current code-bearing assets `/assets/index-DjtEbwVx.js`,
  `/assets/index-DH0EGGDC.css`, `/assets/StratumChat-C9GJIMk2.js`, and
  `/assets/Services-_OuHsgfp.js`, and PDF assets
  `/assets/stratumPDF-Bgc_chGe.js` plus `/assets/pdf-vendor-B7fMFYQc.js`.
- Escalation QA must use `X-Stratum-QA`, `X-Stratum-Eval`, or intercepted SSE.
  Do not trigger live email delivery unless explicitly requested.

## Remaining Control-Plane Work

- GitHub branch protection still needs required checks for frontend
  `CI / build-and-test` and backend `Backend CI / pytest-and-rag`; current
  account/repo controls previously returned a GitHub plan/permission blocker.
- GitHub Actions currently has an account billing/spending-limit blocker for the
  frontend repo; hosted CI for `b51a623` and later pushes cannot be trusted
  until the workflow can start and pass. Backend run `29747403438` for
  `ac6a69a` reproduced the same billing/spending-limit annotation before any
  workflow steps started.
- Cloudflare KV `STRATUM_CONFIG` and `RATE_LIMIT` bindings are not active in
  production.
- Cloudflare D1 persistence is not active until `STRATUM_DB`, `SESSION_SECRET`,
  schema execution, and runtime `persistenceEnabled: true` are configured.
- Railway managed RAG provider activation is pending as described above.
- Voice/TTS activation is pending Railway ElevenLabs credentials plus frontend
  and runtime feature flags.

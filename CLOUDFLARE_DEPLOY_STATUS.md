# STRATUM Deploy Status

Checked on 2026-07-20 UTC after frontend live-smoke command deployment and production smoke.

## Backend

- GitHub repository: `theonlygeranium/stratum-backend`
- Branch: `main`
- Railway project/environment: `sunny-ambition / production`
- Public backend URL: `https://stratum-backend-production-a340.up.railway.app`
- Latest backend code-bearing commit verified for managed RAG plumbing:
  `41b2ae9`
- Latest backend workflow/action-migration commit verified: `f7dced4`
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
- Latest frontend production source/tooling commit verified locally and live:
  `bb8f3b4`
- Latest verified app code-bearing asset commit: `36f201f`; live-smoke
  deployment manifest commit `bb8f3b4` left code-bearing asset hashes
  unchanged.
- Frontend GitHub Actions action-migration commit verified: `d01ce68`;
  frontend CI app-runtime migration commit verified: `f2c969b`;
  CI Playwright server-ownership fix commit `84e01ce` is contained in current
  frontend `main`; Wrangler pin commit `76b97ba` and live-smoke command commit
  `bb8f3b4` are deployed but hosted CI proof is pending because GitHub Actions
  run `29743225634` failed before starting any steps due to an account
  billing/spending-limit blocker.
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
- GitHub Actions run `29743225634` for `bb8f3b4` failed before starting any
  steps because of an account billing/spending-limit blocker; rerun hosted CI
  after billing/settings are corrected.
- Live same-origin `/api/health` on `https://edstratumlabs.ai` proxies Railway
  and returns healthy status.
- Live `/api/config` currently returns `ragEnabled: true`,
  `voiceEnabled: false`, `persistenceEnabled: false`, and
  `maxIntakeQuestions: 6`.
- Live build manifest after the live-smoke deploy returned HTTP 200 with
  `Cache-Control: public, max-age=60, must-revalidate`, commit `bb8f3b4`, the
  Railway backend URL, 13 hashed assets, and unchanged code-bearing assets
  `/assets/index-Cld5-OrE.js`, `/assets/index-DH0EGGDC.css`, and
  `/assets/StratumChat-5iN0axbq.js`.
- Escalation QA must use `X-Stratum-QA`, `X-Stratum-Eval`, or intercepted SSE.
  Do not trigger live email delivery unless explicitly requested.

## Remaining Control-Plane Work

- GitHub branch protection still needs required checks for frontend
  `CI / build-and-test` and backend `Backend CI / pytest-and-rag`; current
  account/repo controls previously returned a GitHub plan/permission blocker.
- GitHub Actions currently has an account billing/spending-limit blocker for the
  frontend repo; hosted CI for `bb8f3b4` and later pushes cannot be trusted
  until the workflow can start and pass. A backend rerun reproduced the same
  billing/spending-limit annotation.
- Cloudflare KV `STRATUM_CONFIG` and `RATE_LIMIT` bindings are not active in
  production.
- Cloudflare D1 persistence is not active until `STRATUM_DB`, `SESSION_SECRET`,
  schema execution, and runtime `persistenceEnabled: true` are configured.
- Railway managed RAG provider activation is pending as described above.
- Voice/TTS activation is pending Railway ElevenLabs credentials plus frontend
  and runtime feature flags.

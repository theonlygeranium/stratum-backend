# STRATUM Live QA And Recommendations

Checked: 2026-07-20 UTC

## Scope

This pass covered the live Cloudflare Pages site, the live Railway backend, and the backend source tree available at `/home/z121532/edstratum-v2/stratum_backend`.

The React/Vite frontend source of truth was not present on this server. The live Pages artifact was already patched and deployed directly to Cloudflare Pages as an operational hotfix. Current production HTML now loads `/assets/index-DISC03.js`, which lazy-loads the discretion-safe STRATUM chat bundle `/assets/StratumChat-DISC03.js`.

Cloudflare Pages source metadata was checked after this pass. The `edstratumlabs` Pages project has `source=null`, and the latest visible deployments are `ad_hoc` direct uploads with empty commit hashes. This confirms the Pages project is not connected to a Git source repository.

## Current Production State

- Frontend: `https://edstratumlabs.ai`
- Cloudflare Pages project: `edstratumlabs`
- Current production entry asset: `/assets/index-DISC03.js`
- Current STRATUM chat asset: `/assets/StratumChat-DISC03.js`
- Backend: `https://stratum-backend-production-a340.up.railway.app`
- Backend runtime: `graph_runtime=langgraph`, `checkpointer=postgres`, `llm_provider=writer`, `llm_model=palmyra-x5`, `embedding_provider=hash`

## QA Results

| Area | Result | Evidence |
|---|---:|---|
| Backend health | Pass | `GET /api/health` returned healthy |
| Backend runtime | Pass | Palmyra/Writer configured; Writer key present; embeddings set to hash |
| Backend tests | Pass | `pytest -q`: 112 passed, 1 skipped |
| RAG eval | Pass | Recall@10 1.0, groundedness proxy 1.0, first-token latency 11.03 ms |
| Deployed conversation matrix | Pass | 54 scenarios, contract pass 1.0, expected behavior 1.0, first-token p95 95.97 ms |
| Docker build | Pass | `docker build -t stratum-backend-liveqa .` completed |
| CORS | Pass | `edstratumlabs.ai`, `www.edstratumlabs.ai`, and `edstratumlabs.pages.dev` preflights returned 200 with matching origin |
| SEO/static assets | Pass | `robots.txt`, `sitemap.xml`, and `og-image.png` returned valid content |
| Security headers | Pass | `x-frame-options`, `x-content-type-options`, `referrer-policy`, `permissions-policy`, and HSTS present |
| Frontend mobile render | Pass | 390x844 Playwright pass; chat opens by normal click |
| Frontend desktop render | Pass | 1440x1000 Playwright pass; chat opens and streams response |
| Frontend asset health | Pass | No failed requests, bad MIME types, or console errors in final pass |
| Discretion copy | Pass | Live chat has no `Jeffrey`, `Jeff`, Calendly, `Talk to Jeffrey`, or `Book a discovery` strings |
| Escalation copy | Pass | Eval-suppressed backend escalation says Founding leadership team, no personal name, no Calendly |

## Rendered QA Details

Browser plugin was not available in this session, so Playwright was used.

Mobile viewport `390x844`:

- Page identity: `EdStratum Labs — AI Strategy & Implementation`
- Chat tab bounding box: `x=337`, `y=361.4`, `width=53`, `height=121.2`
- Normal click opened STRATUM successfully
- Leadership-team chip visible
- Live Canvas roadmap question produced a response
- Console errors: none
- Failed requests: none
- Bad JS/CSS MIME responses: none

Desktop viewport `1440x1000`:

- Page identity: `EdStratum Labs — AI Strategy & Implementation`
- Chat tab bounding box: `x=1387`, `y=439.4`, `width=53`, `height=121.2`
- Normal click opened STRATUM successfully
- Leadership-team chip visible
- Live Canvas roadmap question produced a response
- Console errors: none
- Failed requests: none
- Bad JS/CSS MIME responses: none

Screenshots generated during this pass:

- `/tmp/stratum-liveqa-mobile-home.png`
- `/tmp/stratum-liveqa-mobile-chat-open.png`
- `/tmp/stratum-liveqa-mobile-chat-response.png`
- `/tmp/stratum-liveqa-desktop-home.png`
- `/tmp/stratum-liveqa-desktop-chat-open.png`
- `/tmp/stratum-liveqa-desktop-chat-response.png`

## Findings

No new production-blocking defects were found during this live QA pass.

One operational risk remains: the deployed frontend fix is currently an artifact-level Cloudflare Pages hotfix because the actual React/Vite frontend source tree is not present on this server. Future frontend deploys from the original source could reintroduce the old STRATUM copy unless the source-of-truth repo is located and patched.

Cloudflare does not appear to be able to reveal a hidden source repo for this project. The visible deployment history points to direct-upload deployments, so source recovery should proceed by either obtaining the original project from the human/operator or reconstructing it from `STRATUM_FRONTEND_CONTRACT.md` plus the live bundle.

## Recommendations

1. Locate and patch the frontend source of truth.
   - Apply the same discretion copy changes in the React/Vite source.
   - Commit the real source change so future Cloudflare builds preserve the fix.
   - Add a small `public/build.json` with asset version, backend URL, git SHA, and build timestamp for easier live verification.

2. Add Playwright smoke tests to the frontend project.
   - Assert the STRATUM chat opens on mobile and desktop.
   - Assert no `Jeffrey`, `Jeff`, Calendly, `Talk to Jeffrey`, or `Book a discovery` text appears.
   - Assert `/assets/*.js` responses use a JavaScript MIME type.
   - Assert a normal open-mode chat question reaches the backend and renders a response.

3. Convert the current manual live QA script into a checked-in synthetic monitor.
   - Suggested checks: homepage render, STRATUM open, one open-mode backend request, eval-suppressed escalation request, SEO assets, CORS, and security headers.
   - Run it from CI and optionally from a scheduled monitor.

4. Replace artifact hotfix deployment with source-based Pages deployment.
   - The static artifact deployment worked, but it is harder to audit and repeat.
   - The long-term deploy path should be: source patch -> build -> artifact scan -> Cloudflare Pages deploy.

5. Tighten Cloudflare credential handling.
   - Prefer a scoped Cloudflare API token for Pages deploys instead of a global API key.
   - Keep deployment credentials out of scripts and reports.
   - Rotate any credentials that were previously baked into local deploy helpers.

6. Improve STRATUM interaction polish.
   - Consider changing the small header CTA from `Connect` to `Handoff` or adding a tooltip so users understand it routes to the Founding leadership team.
   - Add an explicit post-escalation state in the frontend that says the summary was prepared or sent, depending on backend delivery status.
   - Keep James mentioned only after confirmed delivery, as the backend already does.

7. Add product analytics for the chat funnel.
   - Track chat open, first message, source-confidence shown, intake completion, escalation intent, and backend error states.
   - Keep analytics privacy-safe; do not log raw conversation text without explicit consent.

8. Add observability around Railway and Resend.
   - Monitor `/api/health`, `/api/runtime`, and representative `/api/chat` latency.
   - Add alerting for failed Resend handoffs or missing `JEFFREY_EMAIL`.
   - Add a dashboard panel for first-token latency and escalation rate.

9. Add a frontend source recovery note to future handoffs.
   - Other agents should know that `/home/z121532/edstratum-v2/stratum_backend` is backend-only.
   - The live frontend source should be recovered or cloned before future design or copy work.
   - Cloudflare Pages metadata currently reports `source=null`, so do not assume a connected Git repo exists.

10. Revisit the visual hierarchy after source is recovered.
    - The chat sidebar works well on mobile and desktop.
    - The header `Connect` label is intentionally brief, but it is slightly ambiguous.
    - A source-level UI pass could improve the escalation CTA clarity without crowding the header.

## Suggested Next Agent Checklist

1. Find the React/Vite frontend repository that produced the `edstratumlabs` Pages build.
2. Patch source STRATUM copy to match `/assets/StratumChat-DISC03.js`.
3. Add frontend Playwright tests for discretion copy and backend streaming.
4. Build from source and confirm the generated bundle has no stale personal-name or Calendly strings.
5. Deploy from source to Cloudflare Pages.
6. Re-run the live QA commands summarized above.

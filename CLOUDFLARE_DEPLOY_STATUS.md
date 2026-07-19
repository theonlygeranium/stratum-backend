# STRATUM Deploy Status

Checked on 2026-07-19 after the Railway-backed STRATUM deployment.

## Backend

- GitHub repository: `theonlygeranium/stratum-backend`
- Branch: `main`
- Latest commit: `519cfde8fac4f4a3dda653fcff6d80ec1b81f013`
- Railway project/environment: `sunny-ambition / production`
- Railway deployment id: `5514940002`
- Railway status: `success`
- Public backend URL: `https://stratum-backend-production-a340.up.railway.app`
- Health check: `GET /api/health` returns `{"status":"healthy","stratum":"online","backend_enabled":true}`

## Cloudflare Pages

- Pages project: `edstratumlabs`
- Production aliases: `https://edstratumlabs.ai`, `https://www.edstratumlabs.ai`
- Pages deployment id: `820a3bbe-ba74-4f80-9e44-dc2e11b1aa5d`
- Pages deployment status: `success`
- Production build-time env var: `VITE_STRATUM_API_URL=https://stratum-backend-production-a340.up.railway.app`
- Live STRATUM chunk includes the Railway URL, `/api/chat`, `fetch(...)`, and `Accept: text/event-stream`.

## Verification

- Backend test suite: `21 passed`
- Docker build: passed with the Railway-compatible `${PORT:-8000}` command.
- Secret/token scan: no matches in tracked backend source.
- Live backend SSE smoke test: passed for open/about/escalation paths.
- Live CORS preflight from `https://edstratumlabs.ai`: passed.
- Live frontend SEO tags: meta description, canonical, OG title, and OG description present.
- Live static files: `/robots.txt`, `/sitemap.xml`, `/og-image.png`, `/_headers`, and `/_redirects` all return HTTP 200.

## Notes

- The local shell is not authenticated to Railway. GitHub deployment statuses confirm Railway production deploy success and expose the public service domain.
- The Railway API token provided during handoff was rejected by Railway as both `RAILWAY_API_TOKEN` and `RAILWAY_TOKEN`, so service variable values were not listed locally.
- Cloudflare credentials remain only in the sensitive handoff attachment and were not committed to this repository.

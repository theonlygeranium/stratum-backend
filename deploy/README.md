# STRATUM Deployment Notes

This backend deploys separately from the existing React/Vite frontend. The backend needs a Python-capable host such as Railway, Fly.io, or another long-running container platform. Cloudflare Pages is only used after the backend is live, to embed the backend URL into the static frontend build.

## Current Workspace Limits

- Backend source is present at `/home/z121532/edstratum-v2/stratum_backend`.
- Frontend source is not present at `/workspace/edstratum-v2`.
- No verified frontend `dist/` artifact is present in this workspace.
- Railway/Fly credentials are not available in this shell.
- Cloudflare credentials live only in the sensitive handoff attachment and should not be copied into docs or committed files.

Run the read-only preflight any time the environment changes:

```bash
./scripts/deployment_readiness.sh
```

## Deployment Order

1. Deploy this backend to Railway, Fly.io, or another long-running Python/container host.
2. Verify `GET /api/health` on the production backend returns `backend_enabled: true`.
3. Set `STRATUM_BACKEND_URL` to that production backend URL.
4. Set `VITE_STRATUM_API_URL` as a Cloudflare Pages production build-time environment variable.
5. Rebuild and redeploy the frontend from a workspace that contains the React/Vite frontend source or a verified `dist/` artifact with `index.html`, `robots.txt`, `sitemap.xml`, `og-image.png`, `_headers`, and `_redirects`.
6. Verify live SEO assets and the frontend-to-backend connection.

Do not run the Cloudflare mutation step until steps 1-3 are complete.

## Backend Host Templates

`railway.json` and `fly.toml` are templates for a Dockerfile-based deploy. They do not contain credentials and do not create/link projects by themselves.

For Railway, an operator with access still needs to install/authenticate the Railway CLI, link or create the target project/service, set production environment variables, and deploy from the backend root.

For Fly.io, an operator with access still needs `flyctl`, app ownership or creation rights, secrets for production environment variables, and DNS/subdomain setup for the chosen backend URL.

## Cloudflare Frontend Wiring

Use `scripts/set_cloudflare_pages_env.sh` only after the backend URL is live:

```bash
DRY_RUN=1 \
STRATUM_BACKEND_URL=https://stratum.edstratumlabs.ai \
./scripts/set_cloudflare_pages_env.sh
```

To perform the actual Cloudflare Pages env update, export Cloudflare credentials from the sensitive handoff, then run:

```bash
CONFIRM_CLOUDFLARE_ENV_UPDATE=yes \
STRATUM_BACKEND_URL=https://stratum.edstratumlabs.ai \
./scripts/set_cloudflare_pages_env.sh
```

This does not redeploy the frontend. Vite embeds `VITE_` variables at build time, so the frontend must be rebuilt and redeployed afterward from the frontend workspace or a verified artifact.

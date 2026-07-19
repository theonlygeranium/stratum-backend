#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_ROOT="${FRONTEND_ROOT:-/workspace/edstratum-v2}"
PAGES_PROJECT="${CLOUDFLARE_PAGES_PROJECT:-edstratumlabs}"
EXIT_CODE=0

ok() {
  printf '[OK]      %s\n' "$*"
}

warn() {
  printf '[WARN]    %s\n' "$*"
}

blocked() {
  printf '[BLOCKED] %s\n' "$*"
  EXIT_CODE=1
}

has_env() {
  local name="$1"
  [[ -n "${!name:-}" ]]
}

echo "STRATUM deployment readiness"
echo "Backend root: ${ROOT}"
echo "Frontend root: ${FRONTEND_ROOT}"
echo

[[ -f "${ROOT}/Dockerfile" ]] && ok "Dockerfile present for Railway/Fly style deploys." || blocked "Dockerfile is missing."
[[ -f "${ROOT}/deploy/railway.json" ]] && ok "Railway deploy template present." || blocked "deploy/railway.json is missing."
[[ -f "${ROOT}/deploy/fly.toml" ]] && ok "Fly deploy template present." || blocked "deploy/fly.toml is missing."
[[ -f "${ROOT}/app/main.py" ]] && ok "FastAPI app source present." || blocked "FastAPI app source is missing."

echo
if [[ -n "${STRATUM_BACKEND_URL:-}" ]]; then
  if [[ "${STRATUM_BACKEND_URL}" == https://* ]]; then
    ok "STRATUM_BACKEND_URL is set to an https URL."
    if command -v curl >/dev/null 2>&1; then
      health_url="${STRATUM_BACKEND_URL%/}/api/health"
      if curl -fsS --max-time 10 "${health_url}" | tr -d '\n' | grep -q '"backend_enabled"[[:space:]]*:[[:space:]]*true'; then
        ok "Remote backend health check passed at ${health_url}."
      else
        blocked "Remote backend health check did not confirm backend_enabled=true at ${health_url}."
      fi
    else
      warn "curl is unavailable; skipped remote backend health check."
    fi
  else
    blocked "STRATUM_BACKEND_URL must be an https production backend URL."
  fi
else
  blocked "STRATUM_BACKEND_URL is unset; Cloudflare Pages must not be pointed at a backend yet."
fi

echo
railway_cli=0
if command -v railway >/dev/null 2>&1; then
  railway_cli=1
  ok "railway CLI is installed."
else
  warn "railway CLI is not installed in this environment."
fi

fly_cli=0
if command -v flyctl >/dev/null 2>&1; then
  fly_cli=1
  ok "flyctl CLI is installed."
else
  warn "flyctl CLI is not installed in this environment."
fi

if [[ "${railway_cli}" -eq 1 ]] && has_env RAILWAY_TOKEN; then
  ok "Railway deploy path has CLI and RAILWAY_TOKEN."
elif [[ "${fly_cli}" -eq 1 ]] && has_env FLY_API_TOKEN; then
  ok "Fly deploy path has CLI and FLY_API_TOKEN."
else
  blocked "No deploy-ready Railway/Fly path is available. Railway needs railway plus RAILWAY_TOKEN; Fly needs flyctl plus FLY_API_TOKEN."
fi

echo
if [[ -d "${FRONTEND_ROOT}" ]]; then
  ok "Frontend source root exists."
else
  blocked "Frontend source root is missing. This backend-only workspace cannot rebuild or redeploy Cloudflare Pages."
fi

dist="${FRONTEND_DIST:-${FRONTEND_ROOT}/dist}"
if [[ -d "${dist}" ]]; then
  ok "Frontend dist directory exists at ${dist}."
  for path in index.html robots.txt sitemap.xml og-image.png _headers _redirects; do
    [[ -f "${dist}/${path}" ]] && ok "dist/${path} present." || blocked "dist/${path} is missing."
  done
else
  blocked "Frontend dist directory is missing at ${dist}."
fi

echo
if has_env CLOUDFLARE_ACCOUNT_ID && has_env CLOUDFLARE_API_KEY && has_env CLOUDFLARE_EMAIL; then
  ok "Cloudflare credentials are exported for Pages project ${PAGES_PROJECT}."
else
  warn "Cloudflare credentials are not exported. Use the sensitive handoff only when a backend URL and frontend deploy artifact are ready."
fi

echo
if [[ "${EXIT_CODE}" -eq 0 ]]; then
  ok "Readiness checks passed. Backend deploy and Cloudflare frontend wiring can proceed in the documented order."
else
  blocked "Deployment remains blocked. Do not mutate Cloudflare or redeploy the frontend from this workspace."
fi

exit "${EXIT_CODE}"

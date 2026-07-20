#!/usr/bin/env bash
set -euo pipefail

: "${STRATUM_BACKEND_URL:?Set STRATUM_BACKEND_URL, for example https://stratum.edstratumlabs.ai}"

PROJECT="${CLOUDFLARE_PAGES_PROJECT:-edstratumlabs}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HUB_ROOT="$(cd "${ROOT}/.." && pwd)"
FRONTEND_ROOT="${FRONTEND_ROOT:-${HUB_ROOT}/edstratum-v2-frontend}"

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

case "${STRATUM_BACKEND_URL}" in
  https://*) ;;
  *) fail "STRATUM_BACKEND_URL must be an https production URL." ;;
esac

case "${STRATUM_BACKEND_URL%/}" in
  https://localhost*|https://127.*|https://example.com|https://stratum-backend.example.com|https://edstratumlabs.ai|https://www.edstratumlabs.ai|https://edstratumlabs.pages.dev|https://*.pages.dev)
    fail "STRATUM_BACKEND_URL must point at the deployed backend, not a frontend/mock/example URL."
    ;;
esac

if [[ "${STRATUM_BACKEND_URL}" == *\"* || "${STRATUM_BACKEND_URL}" == *$'\n'* ]]; then
  fail "STRATUM_BACKEND_URL contains characters this script will not serialize."
fi

if [[ ! -d "${FRONTEND_ROOT}" ]]; then
  echo "Note: frontend source is not present at ${FRONTEND_ROOT}."
  echo "This script can only set the Pages build-time env var; a frontend redeploy must be run from the React/Vite source workspace."
fi

if [[ "${DRY_RUN:-0}" == "1" || "${DRY_RUN:-}" == "true" ]]; then
  echo "Dry run only. No Cloudflare mutation performed."
  echo "Would set Pages project ${PROJECT} production env var:"
  echo "  VITE_STRATUM_API_URL=${STRATUM_BACKEND_URL}"
  exit 0
fi

: "${CLOUDFLARE_ACCOUNT_ID:?Set CLOUDFLARE_ACCOUNT_ID}"
: "${CLOUDFLARE_API_KEY:?Set CLOUDFLARE_API_KEY}"
: "${CLOUDFLARE_EMAIL:?Set CLOUDFLARE_EMAIL}"

if [[ "${CONFIRM_CLOUDFLARE_ENV_UPDATE:-}" != "yes" ]]; then
  fail "Set CONFIRM_CLOUDFLARE_ENV_UPDATE=yes to mutate Cloudflare Pages. Run with DRY_RUN=1 first when in doubt."
fi

response_file="$(mktemp)"
trap 'rm -f "${response_file}"' EXIT

http_code="$(
  curl -sS -o "${response_file}" -w "%{http_code}" -X PATCH \
  "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/pages/projects/${PROJECT}" \
  -H "X-Auth-Email: ${CLOUDFLARE_EMAIL}" \
  -H "X-Auth-Key: ${CLOUDFLARE_API_KEY}" \
  -H "Content-Type: application/json" \
  -d @- <<JSON
{
  "deployment_configs": {
    "production": {
      "env_vars": {
        "VITE_STRATUM_API_URL": {
          "type": "plain_text",
          "value": "${STRATUM_BACKEND_URL}"
        }
      }
    }
  }
}
JSON
)"

if [[ ! "${http_code}" =~ ^2 ]]; then
  echo "Cloudflare Pages env update failed with HTTP ${http_code}." >&2
  echo "Response body suppressed to avoid logging project environment values." >&2
  exit 1
fi

if ! grep -q '"success"[[:space:]]*:[[:space:]]*true' "${response_file}"; then
  echo "Cloudflare Pages env update did not return success=true." >&2
  echo "Response body suppressed to avoid logging project environment values." >&2
  exit 1
fi

echo
echo "Cloudflare Pages production env var VITE_STRATUM_API_URL is set for ${PROJECT}."
echo "Trigger a fresh frontend deployment from the React/Vite workspace so Vite embeds the value."

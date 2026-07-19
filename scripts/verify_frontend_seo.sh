#!/usr/bin/env bash
set -euo pipefail

url="${1:-https://edstratumlabs.ai}"
frontend_root="${FRONTEND_ROOT:-/workspace/edstratum-v2}"
dist="${FRONTEND_DIST:-${frontend_root}/dist}"
exit_code=0

check() {
  printf '[OK]      %s\n' "$*"
}

warn() {
  printf '[WARN]    %s\n' "$*"
}

fail() {
  printf '[FAIL]    %s\n' "$*"
  exit_code=1
}

tmp_html="$(mktemp)"
trap 'rm -f "${tmp_html}"' EXIT

echo "Checking live frontend SEO at ${url}"
curl -fsS --max-time 15 "${url}" >"${tmp_html}"

grep -qi 'og:title' "${tmp_html}" && check "Open Graph title is present." || fail "Open Graph title is missing."
grep -qi 'name="description"' "${tmp_html}" && check "Meta description is present." || fail "Meta description is missing."
grep -qi 'rel="canonical"' "${tmp_html}" && check "Canonical link is present." || fail "Canonical link is missing."

for path in robots.txt sitemap.xml og-image.png; do
  if curl -fsS --max-time 15 -o /dev/null "${url%/}/${path}"; then
    check "Live ${path} is reachable."
  else
    fail "Live ${path} is not reachable."
  fi
done

if [[ -d "${dist}" ]]; then
  echo
  echo "Checking local pre-deploy artifact at ${dist}"
  for path in index.html robots.txt sitemap.xml og-image.png _headers _redirects; do
    [[ -f "${dist}/${path}" ]] && check "dist/${path} is present." || fail "dist/${path} is missing."
  done
else
  echo
  warn "No local frontend dist found at ${dist}; skipped pre-deploy SEO artifact checks."
  warn "This is expected in the backend-only workspace."
fi

exit "${exit_code}"

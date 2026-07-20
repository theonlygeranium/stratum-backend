#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if ! command -v railway >/dev/null 2>&1 && [[ -f "${HOME}/.railway/env" ]]; then
  # shellcheck disable=SC1091
  source "${HOME}/.railway/env"
fi

PROJECT_NAME="${RAILWAY_PROJECT_NAME:-stratum-backend}"
SERVICE_NAME="${RAILWAY_SERVICE_NAME:-stratum-backend}"
GITHUB_REPO="${GITHUB_REPO:-theonlygeranium/stratum-backend}"
BRANCH="${RAILWAY_BRANCH:-main}"
ENVIRONMENT="${RAILWAY_ENVIRONMENT:-production}"

export ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-https://edstratumlabs.ai,https://www.edstratumlabs.ai,https://edstratumlabs.pages.dev,http://localhost:5173}"
export ESCALATION_EMAIL_TO="${ESCALATION_EMAIL_TO:-${JEFFREY_EMAIL:-}}"
export ESCALATION_EMAIL_FROM="${ESCALATION_EMAIL_FROM:-${RESEND_FROM_EMAIL:-}}"

required_env=(OPENAI_API_KEY DATABASE_URL ALLOWED_ORIGINS RESEND_API_KEY ESCALATION_EMAIL_TO)

fail() {
  printf '[BLOCKED] %s\n' "$*" >&2
  exit 1
}

ok() {
  printf '[OK] %s\n' "$*"
}

[[ -f Dockerfile ]] || fail "Dockerfile is missing from ${ROOT}."
[[ -f railway.json ]] || fail "railway.json is missing from ${ROOT}."
command -v railway >/dev/null 2>&1 || fail "Railway CLI is not installed. Run: bash <(curl -fsSL railway.com/install.sh) -y"
command -v jq >/dev/null 2>&1 || fail "jq is required for JSON parsing."

missing=()
for key in "${required_env[@]}"; do
  [[ -n "${!key:-}" ]] || missing+=("${key}")
done
if [[ "${#missing[@]}" -gt 0 ]]; then
  fail "Missing required backend env vars: ${missing[*]}. Do not use placeholder secret values."
fi

if [[ -n "${RAILWAY_API_TOKEN:-}" && -n "${RAILWAY_TOKEN:-}" ]]; then
  fail "Set only one Railway auth token. Railway CLI rejects simultaneous RAILWAY_API_TOKEN and RAILWAY_TOKEN."
fi

if [[ -z "${RAILWAY_API_TOKEN:-}" && -z "${RAILWAY_TOKEN:-}" ]]; then
  railway whoami >/dev/null 2>&1 || fail "Railway is not authenticated. Export RAILWAY_API_TOKEN for new project creation or run 'railway login --browserless'."
fi

if [[ -n "${RAILWAY_PROJECT_ID:-}" ]]; then
  railway link --project "${RAILWAY_PROJECT_ID}" --environment "${ENVIRONMENT}" --json >/dev/null
  ok "Linked Railway project ${RAILWAY_PROJECT_ID}."
elif [[ ! -f .railway/project.json ]]; then
  if [[ -n "${RAILWAY_TOKEN:-}" && -z "${RAILWAY_API_TOKEN:-}" ]]; then
    fail "A project-scoped RAILWAY_TOKEN cannot create a new project. Export RAILWAY_API_TOKEN or run an interactive Railway login."
  fi
  railway init --name "${PROJECT_NAME}" --json >/dev/null
  ok "Created and linked Railway project ${PROJECT_NAME}."
else
  ok "Using existing Railway link in .railway/project.json."
fi

service_exists=0
if services_json="$(railway service list --json 2>/dev/null)"; then
  if jq -e --arg name "${SERVICE_NAME}" '.[]? | select(.name == $name)' >/dev/null <<<"${services_json}"; then
    service_exists=1
  fi
fi

if [[ "${service_exists}" -eq 0 ]]; then
  railway add --repo "${GITHUB_REPO}" --branch "${BRANCH}" --service "${SERVICE_NAME}" --json >/dev/null
  ok "Created Railway service ${SERVICE_NAME} from ${GITHUB_REPO}@${BRANCH}."
else
  railway service source connect --repo "${GITHUB_REPO}" --branch "${BRANCH}" --service "${SERVICE_NAME}" --json >/dev/null
  ok "Confirmed Railway service ${SERVICE_NAME} is connected to ${GITHUB_REPO}@${BRANCH}."
fi

for key in "${required_env[@]}"; do
  printf '%s' "${!key}" | railway variable set "${key}" --stdin --service "${SERVICE_NAME}" --environment "${ENVIRONMENT}" --skip-deploys --json >/dev/null
  ok "Set ${key} on Railway service ${SERVICE_NAME}."
done

railway service redeploy --service "${SERVICE_NAME}" --environment "${ENVIRONMENT}" --from-source --yes --json >/dev/null
ok "Triggered Railway source redeploy."

if domains_json="$(railway domain list --service "${SERVICE_NAME}" --environment "${ENVIRONMENT}" --json 2>/dev/null)"; then
  public_domain="$(jq -r '[.[]? | select(.domain | endswith(".up.railway.app")) | .domain][0] // empty' <<<"${domains_json}")"
else
  public_domain=""
fi

if [[ -z "${public_domain}" ]]; then
  domain_json="$(railway domain --service "${SERVICE_NAME}" --environment "${ENVIRONMENT}" --json)"
  public_domain="$(jq -r '.domain // .url // empty' <<<"${domain_json}")"
fi

if [[ -n "${public_domain}" ]]; then
  case "${public_domain}" in
    http*) backend_url="${public_domain}" ;;
    *) backend_url="https://${public_domain}" ;;
  esac
  ok "Railway public URL assigned: ${backend_url}"
  printf '%s\n' "${backend_url}" > .railway/stratum_backend_url.txt
else
  fail "Railway deploy started, but no public domain was returned. Check 'railway domain list --service ${SERVICE_NAME} --json'."
fi

railway deployment list --service "${SERVICE_NAME}" --environment "${ENVIRONMENT}" --limit 5 --json > .railway/latest_deployments.json
ok "Wrote Railway deployment snapshot to .railway/latest_deployments.json."

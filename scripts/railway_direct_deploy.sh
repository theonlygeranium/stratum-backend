#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

fail() {
  printf '[BLOCKED] %s\n' "$*" >&2
  exit 1
}

ok() {
  printf '[OK] %s\n' "$*"
}

warn() {
  printf '[WARN] %s\n' "$*" >&2
}

if [[ "${CONFIRM_DIRECT_RAILWAY_DEPLOY:-}" != "yes" ]]; then
  fail "Direct Railway deploys bypass the GitHub-connected source deploy path. Set CONFIRM_DIRECT_RAILWAY_DEPLOY=yes to continue."
fi

PROJECT_ID="${RAILWAY_PROJECT_ID:-}"
SERVICE_NAME="${RAILWAY_SERVICE_NAME:-stratum-backend}"
ENVIRONMENT="${RAILWAY_ENVIRONMENT:-production}"
DEPLOY_MESSAGE="${DEPLOY_MESSAGE:-Emergency direct deploy from local source: $(git rev-parse --short HEAD 2>/dev/null || date -u '+%Y-%m-%d %H:%M UTC')}"
DEPLOY_TIMEOUT_SECONDS="${DEPLOY_TIMEOUT_SECONDS:-600}"
DEPLOY_POLL_SECONDS="${DEPLOY_POLL_SECONDS:-15}"
BACKEND_SMOKE_URL="${BACKEND_SMOKE_URL:-${STRATUM_BACKEND_URL:-https://stratum-backend-production-a340.up.railway.app}}"
RAILWAY_CALLER_VALUE="${RAILWAY_CALLER:-skill:use-railway@1.3.5}"
RAILWAY_AGENT_SESSION_VALUE="${RAILWAY_AGENT_SESSION:-railway-direct-deploy-$(date +%s)-$$}"

[[ -f Dockerfile ]] || fail "Dockerfile is missing from ${ROOT}."
[[ -f railway.json ]] || fail "railway.json is missing from ${ROOT}."

if [[ "${DRY_RUN:-}" == "1" ]]; then
  ok "Dry run only. No Railway deploy will be started."
  ok "Would deploy local source to service=${SERVICE_NAME} environment=${ENVIRONMENT}${PROJECT_ID:+ project=${PROJECT_ID}}."
  ok "Would run: railway up${PROJECT_ID:+ --project ${PROJECT_ID}} --service ${SERVICE_NAME} --environment ${ENVIRONMENT} --detach -m <redacted summary>"
  ok "Would poll Railway deployment status until SUCCESS/FAILED/CRASHED/timeout."
  if [[ "${SKIP_BACKEND_SMOKE:-}" == "yes" ]]; then
    ok "Would skip backend live smoke because SKIP_BACKEND_SMOKE=yes."
  else
    ok "Would run scripts/live_backend_smoke.py against ${BACKEND_SMOKE_URL}."
  fi
  exit 0
fi

if ! command -v railway >/dev/null 2>&1 && [[ -f "${HOME}/.railway/env" ]]; then
  # shellcheck disable=SC1091
  source "${HOME}/.railway/env"
fi

command -v railway >/dev/null 2>&1 || fail "Railway CLI is not installed. Run: bash <(curl -fsSL https://railway.com/install.sh) --agents -y"
command -v jq >/dev/null 2>&1 || fail "jq is required for deployment status polling."

if [[ -n "${RAILWAY_API_TOKEN:-}" && -n "${RAILWAY_TOKEN:-}" ]]; then
  fail "Set only one Railway auth token. Railway CLI rejects simultaneous RAILWAY_API_TOKEN and RAILWAY_TOKEN."
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  if [[ "${ALLOW_DIRTY_DIRECT_DEPLOY:-}" != "yes" ]]; then
    fail "Worktree has uncommitted changes. Commit first, or set ALLOW_DIRTY_DIRECT_DEPLOY=yes for an urgent direct deploy that will be copied to GitHub later."
  fi
  warn "Deploying with uncommitted local changes because ALLOW_DIRTY_DIRECT_DEPLOY=yes."
fi

run_railway() {
  RAILWAY_CALLER="${RAILWAY_CALLER_VALUE}" \
    RAILWAY_AGENT_SESSION="${RAILWAY_AGENT_SESSION_VALUE}" \
    railway "$@"
}

deploy_args=(up --service "${SERVICE_NAME}" --environment "${ENVIRONMENT}" --detach -m "${DEPLOY_MESSAGE}")
list_args=(deployment list --service "${SERVICE_NAME}" --environment "${ENVIRONMENT}" --limit 1 --json)
logs_args=(logs --service "${SERVICE_NAME}" --environment "${ENVIRONMENT}" --lines 100 --json)
if [[ -n "${PROJECT_ID}" ]]; then
  deploy_args=(up --project "${PROJECT_ID}" --environment "${ENVIRONMENT}" --service "${SERVICE_NAME}" --detach -m "${DEPLOY_MESSAGE}")
  list_args=(deployment list --project "${PROJECT_ID}" --environment "${ENVIRONMENT}" --service "${SERVICE_NAME}" --limit 1 --json)
  logs_args=(logs --project "${PROJECT_ID}" --environment "${ENVIRONMENT}" --service "${SERVICE_NAME}" --lines 100 --json)
fi

ok "Starting direct Railway deploy from local source."
ok "Target service=${SERVICE_NAME} environment=${ENVIRONMENT}${PROJECT_ID:+ project=${PROJECT_ID}}."
run_railway "${deploy_args[@]}"
ok "Deploy queued. Polling Railway until a terminal deployment status is observed."

mkdir -p .railway
deadline=$((SECONDS + DEPLOY_TIMEOUT_SECONDS))
latest_json=""
latest_id=""
latest_status=""

while (( SECONDS < deadline )); do
  latest_json="$(run_railway "${list_args[@]}")"
  latest_status="$(
    jq -r '
      if type == "array" then
        .[0].status // empty
      elif has("deployments") then
        .deployments[0].status // empty
      else
        .status // empty
      end
    ' <<<"${latest_json}"
  )"
  latest_id="$(
    jq -r '
      if type == "array" then
        .[0].id // empty
      elif has("deployments") then
        .deployments[0].id // empty
      else
        .id // empty
      end
    ' <<<"${latest_json}"
  )"
  printf '%s\n' "${latest_json}" > .railway/direct_deploy_latest.json

  case "${latest_status}" in
    SUCCESS)
      ok "Railway deployment reached SUCCESS${latest_id:+ (${latest_id})}."
      break
      ;;
    FAILED|CRASHED)
      warn "Railway deployment reached ${latest_status}${latest_id:+ (${latest_id})}."
      run_railway "${logs_args[@]}" > .railway/direct_deploy_failure_logs.json || true
      fail "Direct Railway deploy failed. Recent bounded logs were written to .railway/direct_deploy_failure_logs.json."
      ;;
    NEEDS_APPROVAL|SLEEPING|SKIPPED|REMOVED|REMOVING)
      fail "Railway deployment stopped in non-success state ${latest_status}${latest_id:+ (${latest_id})}."
      ;;
    QUEUED|INITIALIZING|WAITING|BUILDING|DEPLOYING|"")
      ok "Railway deployment status: ${latest_status:-unknown}${latest_id:+ (${latest_id})}."
      ;;
    *)
      warn "Railway deployment status is unexpected: ${latest_status}${latest_id:+ (${latest_id})}."
      ;;
  esac

  sleep "${DEPLOY_POLL_SECONDS}"
done

if [[ "${latest_status}" != "SUCCESS" ]]; then
  fail "Timed out after ${DEPLOY_TIMEOUT_SECONDS}s waiting for Railway deployment success. Latest status: ${latest_status:-unknown}${latest_id:+ (${latest_id})}."
fi

if [[ "${SKIP_BACKEND_SMOKE:-}" == "yes" ]]; then
  ok "Skipped backend live smoke because SKIP_BACKEND_SMOKE=yes."
else
  python_bin="${PYTHON_BIN:-.venv/bin/python}"
  if [[ ! -x "${python_bin}" ]]; then
    python_bin="${PYTHON_BIN:-python3}"
  fi
  ok "Running safe backend live smoke against ${BACKEND_SMOKE_URL}."
  "${python_bin}" scripts/live_backend_smoke.py --url "${BACKEND_SMOKE_URL}"
fi

ok "Direct Railway deploy verified."

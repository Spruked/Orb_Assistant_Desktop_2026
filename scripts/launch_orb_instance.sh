#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTANCE_ENV="${ORB_INSTANCE_ENV:-${REPO_ROOT}/.orb-instance.env}"

if [[ -f "${INSTANCE_ENV}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${INSTANCE_ENV}"
  set +a
fi

LOG_ROOT="${ORB_SYSTEM_ROOT:-${REPO_ROOT}}/logs"
mkdir -p "${LOG_ROOT}"
ORB_LAUNCH_LOG="${ORB_LAUNCH_LOG:-${LOG_ROOT}/orb-${ORB_INSTANCE_ID:-desktop}.log}"

cd "${REPO_ROOT}/electron"
if [[ "${ORB_FOREGROUND:-0}" == "1" ]]; then
  exec env -u ELECTRON_RUN_AS_NODE ./node_modules/.bin/electron . --disable-http-cache
fi

if [[ "${ORB_DETACH:-0}" == "1" ]]; then
  nohup env -u ELECTRON_RUN_AS_NODE ./node_modules/.bin/electron . --disable-http-cache >>"${ORB_LAUNCH_LOG}" 2>&1 < /dev/null &
  ORB_PID=$!
  echo "${ORB_PID}" > "${REPO_ROOT}/.orb-instance.pid"
  echo "Orb instance launched in background"
  echo "PID: ${ORB_PID}"
  echo "Log: ${ORB_LAUNCH_LOG}"
  exit 0
fi

echo "Orb instance launching"
echo "Log: ${ORB_LAUNCH_LOG}"
exec env -u ELECTRON_RUN_AS_NODE ./node_modules/.bin/electron . --disable-http-cache >>"${ORB_LAUNCH_LOG}" 2>&1

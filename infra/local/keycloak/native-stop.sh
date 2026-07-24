#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
state_dir="${VFBIZ_KEYCLOAK_STATE_DIR:-${repo_root}/local-data/keycloak/native}"
pid_file="${state_dir}/keycloak.pid"

if [[ ! -f "${pid_file}" ]]; then
  echo "Keycloak is not running."
  exit 0
fi

keycloak_pid="$(cat "${pid_file}")"
if kill -0 "${keycloak_pid}" 2>/dev/null; then
  kill "${keycloak_pid}"
  for _ in $(seq 1 30); do
    kill -0 "${keycloak_pid}" 2>/dev/null || break
    sleep 1
  done
fi

if kill -0 "${keycloak_pid}" 2>/dev/null; then
  echo "Keycloak PID ${keycloak_pid} did not stop cleanly." >&2
  exit 1
fi

rm -f "${pid_file}"
echo "Keycloak stopped."

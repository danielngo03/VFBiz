#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
keycloak_home="${VFBIZ_KEYCLOAK_HOME:-${repo_root}/local-data/keycloak/keycloak-26.7.0}"
state_dir="${VFBIZ_KEYCLOAK_STATE_DIR:-${repo_root}/local-data/keycloak/native}"
environment_file="${state_dir}/.env"
pid_file="${state_dir}/keycloak.pid"
log_file="${state_dir}/keycloak.log"

"$(dirname "${BASH_SOURCE[0]}")/native-bootstrap.sh"
"$(dirname "${BASH_SOURCE[0]}")/native-install-theme.sh"

set -a
# shellcheck disable=SC1090
source "${environment_file}"
set +a

if [[ -f "${pid_file}" ]] && kill -0 "$(cat "${pid_file}")" 2>/dev/null; then
  "$(dirname "${BASH_SOURCE[0]}")/native-reconcile.sh"
  echo "Keycloak is already running with PID $(cat "${pid_file}")."
  exit 0
fi

export JAVA_HOME="/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home"
export KC_DB="postgres"
export KC_DB_URL="jdbc:postgresql://127.0.0.1:5434/vfbiz_keycloak"
export KC_HEALTH_ENABLED="true"
export KC_METRICS_ENABLED="true"

nohup "${keycloak_home}/bin/kc.sh" start-dev \
  --http-host=127.0.0.1 \
  --http-port=8080 \
  --hostname=http://127.0.0.1:8080 \
  --spi-theme--static-max-age=-1 \
  --spi-theme--cache-themes=false \
  --spi-theme--cache-templates=false \
  --import-realm \
  >"${log_file}" 2>&1 &
keycloak_pid=$!
printf '%s\n' "${keycloak_pid}" >"${pid_file}"

for _ in $(seq 1 90); do
  if curl --fail --silent --max-time 2 \
    "http://127.0.0.1:8080/realms/vfbiz-customer/.well-known/openid-configuration" \
    >/dev/null; then
    "$(dirname "${BASH_SOURCE[0]}")/native-reconcile.sh"
    echo "Keycloak is ready on http://127.0.0.1:8080 (PID ${keycloak_pid})."
    exit 0
  fi
  if ! kill -0 "${keycloak_pid}" 2>/dev/null; then
    echo "Keycloak exited during startup. Inspect ${log_file}." >&2
    exit 1
  fi
  sleep 1
done

echo "Keycloak did not become ready within 90 seconds. Inspect ${log_file}." >&2
exit 1

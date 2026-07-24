#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
keycloak_version="26.7.0"
keycloak_home="${VFBIZ_KEYCLOAK_HOME:-${repo_root}/local-data/keycloak/keycloak-${keycloak_version}}"
state_dir="${VFBIZ_KEYCLOAK_STATE_DIR:-${repo_root}/local-data/keycloak/native}"
environment_file="${state_dir}/.env"
postgres_bin="${VFBIZ_POSTGRES_BIN:-/opt/homebrew/opt/postgresql@17/bin}"
postgres_host="${VFBIZ_POSTGRES_HOST:-127.0.0.1}"
postgres_port="${VFBIZ_POSTGRES_PORT:-5434}"
postgres_admin_user="${VFBIZ_POSTGRES_ADMIN_USER:-${USER}}"

if [[ ! -x "${keycloak_home}/bin/kc.sh" ]]; then
  echo "Keycloak ${keycloak_version} is missing at ${keycloak_home}." >&2
  exit 1
fi

if [[ ! -x /opt/homebrew/opt/openjdk@25/bin/java ]]; then
  echo "OpenJDK 25 is required at /opt/homebrew/opt/openjdk@25." >&2
  exit 1
fi

mkdir -p "${state_dir}" "${keycloak_home}/data/import"
chmod 700 "${state_dir}"

if [[ ! -f "${environment_file}" ]]; then
  umask 077
  {
    printf 'KC_BOOTSTRAP_ADMIN_USERNAME=%s\n' 'vfbiz-local-admin'
    printf 'KC_BOOTSTRAP_ADMIN_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'KC_DB_USERNAME=%s\n' 'vfbiz_keycloak'
    printf 'KC_DB_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'VFBIZ_CUSTOMER_OIDC_CLIENT_SECRET=%s\n' "$(openssl rand -hex 24)"
    printf 'VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_SECRET=%s\n' "$(openssl rand -hex 24)"
    printf 'VFBIZ_WORKFORCE_OIDC_CLIENT_SECRET=%s\n' "$(openssl rand -hex 24)"
  } >"${environment_file}"
fi

if ! grep -q '^VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_SECRET=' "${environment_file}"; then
  umask 077
  printf 'VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_SECRET=%s\n' \
    "$(openssl rand -hex 24)" >>"${environment_file}"
fi

set -a
# shellcheck disable=SC1090
source "${environment_file}"
set +a

"${postgres_bin}/psql" \
  --host "${postgres_host}" \
  --port "${postgres_port}" \
  --username "${postgres_admin_user}" \
  --dbname postgres \
  --set=app_user="${KC_DB_USERNAME}" \
  --set=app_password="${KC_DB_PASSWORD}" <<'SQL'
SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE',
  :'app_user',
  :'app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
\gexec
SQL

"${postgres_bin}/psql" \
  --host "${postgres_host}" \
  --port "${postgres_port}" \
  --username "${postgres_admin_user}" \
  --dbname postgres \
  --set=app_database="vfbiz_keycloak" \
  --set=app_user="${KC_DB_USERNAME}" <<'SQL'
SELECT format('CREATE DATABASE %I OWNER %I', :'app_database', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app_database')
\gexec
SQL

rm -f \
  "${keycloak_home}/data/import/customer-realm.json" \
  "${keycloak_home}/data/import/workforce-realm.json"
cp \
  "${repo_root}/infra/local/keycloak/realms/customer-realm.json" \
  "${keycloak_home}/data/import/vfbiz-customer-realm.json"
cp \
  "${repo_root}/infra/local/keycloak/realms/workforce-realm.json" \
  "${keycloak_home}/data/import/vfbiz-workforce-realm.json"

echo "Native Keycloak dependencies are ready. Secrets: ${environment_file}"

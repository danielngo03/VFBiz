#!/usr/bin/env bash
set -euo pipefail

postgres_bin="${VFBIZ_POSTGRES_BIN:-/opt/homebrew/opt/postgresql@17/bin}"
postgres_host="${VFBIZ_POSTGRES_HOST:-127.0.0.1}"
postgres_port="${VFBIZ_POSTGRES_PORT:-5434}"
postgres_admin_database="${VFBIZ_POSTGRES_ADMIN_DATABASE:-postgres}"
postgres_admin_user="${VFBIZ_POSTGRES_ADMIN_USER:-${USER}}"
app_database="${VFBIZ_POSTGRES_DATABASE:-vfbiz}"
app_user="${VFBIZ_POSTGRES_USER:-vfbiz}"
app_password="${VFBIZ_POSTGRES_PASSWORD:-vfbiz}"

if [[ ! "${app_database}" =~ ^[a-z][a-z0-9_]{0,62}$ ]]; then
  echo "Invalid local database name: ${app_database}" >&2
  exit 1
fi

if [[ ! "${app_user}" =~ ^[a-z][a-z0-9_]{0,62}$ ]]; then
  echo "Invalid local role name: ${app_user}" >&2
  exit 1
fi

for command_name in psql pg_isready; do
  if [[ ! -x "${postgres_bin}/${command_name}" ]]; then
    echo "Missing PostgreSQL 17 command: ${postgres_bin}/${command_name}" >&2
    exit 1
  fi
done

"${postgres_bin}/pg_isready" \
  --host "${postgres_host}" \
  --port "${postgres_port}" \
  --dbname "${postgres_admin_database}" >/dev/null

"${postgres_bin}/psql" \
  --host "${postgres_host}" \
  --port "${postgres_port}" \
  --username "${postgres_admin_user}" \
  --dbname "${postgres_admin_database}" \
  --set=app_user="${app_user}" \
  --set=app_password="${app_password}" <<'SQL'
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
  --dbname "${postgres_admin_database}" \
  --set=app_database="${app_database}" \
  --set=app_user="${app_user}" <<'SQL'
SELECT format('CREATE DATABASE %I OWNER %I', :'app_database', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app_database')
\gexec
SQL

"${postgres_bin}/psql" \
  --host "${postgres_host}" \
  --port "${postgres_port}" \
  --username "${postgres_admin_user}" \
  --dbname "${app_database}" \
  --command "CREATE EXTENSION IF NOT EXISTS postgis"

"$(dirname "${BASH_SOURCE[0]}")/preflight-local-database.sh"

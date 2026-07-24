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

server_version="$(
  "${postgres_bin}/psql" \
    --host "${postgres_host}" \
    --port "${postgres_port}" \
    --username "${postgres_admin_user}" \
    --dbname "${postgres_admin_database}" \
    --tuples-only \
    --no-align \
    --command "SHOW server_version_num"
)"

if (( server_version < 170000 || server_version >= 180000 )); then
  echo "Unsupported PostgreSQL version number: ${server_version}. Expected PostgreSQL 17.x." >&2
  exit 1
fi

postgis_available="$(
  "${postgres_bin}/psql" \
    --host "${postgres_host}" \
    --port "${postgres_port}" \
    --username "${postgres_admin_user}" \
    --dbname "${postgres_admin_database}" \
    --tuples-only \
    --no-align \
    --command "SELECT default_version FROM pg_available_extensions WHERE name = 'postgis'"
)"

if [[ -z "${postgis_available}" ]]; then
  echo "PostGIS is not available to PostgreSQL 17." >&2
  exit 1
fi

role_exists="$(
  "${postgres_bin}/psql" \
    --host "${postgres_host}" \
    --port "${postgres_port}" \
    --username "${postgres_admin_user}" \
    --dbname "${postgres_admin_database}" \
    --tuples-only \
    --no-align \
    --set=app_user="${app_user}" <<'SQL'
SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user');
SQL
)"

database_exists="$(
  "${postgres_bin}/psql" \
    --host "${postgres_host}" \
    --port "${postgres_port}" \
    --username "${postgres_admin_user}" \
    --dbname "${postgres_admin_database}" \
    --tuples-only \
    --no-align \
    --set=app_database="${app_database}" <<'SQL'
SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app_database');
SQL
)"

if [[ "${role_exists}" != "t" || "${database_exists}" != "t" ]]; then
  echo "VFBiz role or database is missing. Run npm run db:local:bootstrap --workspace @vfbiz/api." >&2
  exit 1
fi

installed_postgis="$(
  PGPASSWORD="${app_password}" "${postgres_bin}/psql" \
    --host "${postgres_host}" \
    --port "${postgres_port}" \
    --username "${app_user}" \
    --dbname "${app_database}" \
    --tuples-only \
    --no-align \
    --command "SELECT extversion FROM pg_extension WHERE extname = 'postgis'"
)"

if [[ -z "${installed_postgis}" ]]; then
  echo "PostGIS is available but not enabled in database ${app_database}." >&2
  exit 1
fi

echo "Local database ready: PostgreSQL 17, PostGIS ${installed_postgis}, ${postgres_host}:${postgres_port}/${app_database}."

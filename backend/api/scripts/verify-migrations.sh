#!/usr/bin/env bash
set -euo pipefail

repo_api_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
postgres_bin="${VFBIZ_POSTGRES_BIN:-/opt/homebrew/opt/postgresql@17/bin}"
postgres_host="${VFBIZ_POSTGRES_HOST:-127.0.0.1}"
postgres_port="${VFBIZ_POSTGRES_PORT:-5434}"
postgres_admin_database="${VFBIZ_POSTGRES_ADMIN_DATABASE:-postgres}"
postgres_admin_user="${VFBIZ_POSTGRES_ADMIN_USER:-${USER}}"
database_suffix="${$}"
clean_database="vfbiz_migration_clean_${database_suffix}"
legacy_database="vfbiz_migration_legacy_${database_suffix}"

if [[ ! "${postgres_admin_user}" =~ ^[a-zA-Z_][a-zA-Z0-9_]{0,62}$ ]]; then
  echo "Invalid PostgreSQL admin role: ${postgres_admin_user}" >&2
  exit 1
fi

for command_name in psql createdb dropdb pg_isready; do
  if [[ ! -x "${postgres_bin}/${command_name}" ]]; then
    echo "Missing PostgreSQL 17 command: ${postgres_bin}/${command_name}" >&2
    exit 1
  fi
done

cleanup() {
  "${postgres_bin}/dropdb" \
    --host "${postgres_host}" \
    --port "${postgres_port}" \
    --username "${postgres_admin_user}" \
    --if-exists \
    --force \
    "${clean_database}" >/dev/null 2>&1 || true
  "${postgres_bin}/dropdb" \
    --host "${postgres_host}" \
    --port "${postgres_port}" \
    --username "${postgres_admin_user}" \
    --if-exists \
    --force \
    "${legacy_database}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

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
  echo "Migration replay requires PostgreSQL 17.x; observed ${server_version}." >&2
  exit 1
fi

create_test_database() {
  local database_name="$1"
  "${postgres_bin}/createdb" \
    --host "${postgres_host}" \
    --port "${postgres_port}" \
    --username "${postgres_admin_user}" \
    "${database_name}"
  "${postgres_bin}/psql" \
    --host "${postgres_host}" \
    --port "${postgres_port}" \
    --username "${postgres_admin_user}" \
    --dbname "${database_name}" \
    --set=ON_ERROR_STOP=1 \
    --command "CREATE EXTENSION IF NOT EXISTS postgis" >/dev/null
}

connection_url() {
  local database_name="$1"
  printf 'postgresql://%s@%s:%s/%s' \
    "${postgres_admin_user}" \
    "${postgres_host}" \
    "${postgres_port}" \
    "${database_name}"
}

create_test_database "${clean_database}"
clean_url="$(connection_url "${clean_database}")"

(
  cd "${repo_api_dir}"
  VFBIZ_DATABASE_URL="${clean_url}" npx prisma migrate deploy --config prisma.config.ts
  drift="$(
    VFBIZ_DATABASE_URL="${clean_url}" \
      npx prisma migrate diff \
        --from-config-datasource \
        --to-schema prisma \
        --script \
        --config prisma.config.ts
  )"
  grep -q -- '-- This is an empty migration.' <<<"${drift}"
  VFBIZ_TEST_DATABASE_URL="${clean_url}" \
    VFBIZ_DATABASE_URL="${clean_url}" \
    NODE_OPTIONS=--experimental-vm-modules \
    npx jest --config ./test/jest-postgres.json --runInBand
)

create_test_database "${legacy_database}"
legacy_url="$(connection_url "${legacy_database}")"

"${postgres_bin}/psql" \
  --host "${postgres_host}" \
  --port "${postgres_port}" \
  --username "${postgres_admin_user}" \
  --dbname "${legacy_database}" \
  --set=ON_ERROR_STOP=1 \
  --file "${repo_api_dir}/prisma/migrations/20260722160000_platform_foundation/migration.sql" >/dev/null
"${postgres_bin}/psql" \
  --host "${postgres_host}" \
  --port "${postgres_port}" \
  --username "${postgres_admin_user}" \
  --dbname "${legacy_database}" \
  --set=ON_ERROR_STOP=1 \
  --file "${repo_api_dir}/test/fixtures/legacy-staging.sql" >/dev/null

(
  cd "${repo_api_dir}"
  VFBIZ_DATABASE_URL="${legacy_url}" \
    npx prisma migrate resolve \
      --applied 20260722160000_platform_foundation \
      --config prisma.config.ts
  VFBIZ_DATABASE_URL="${legacy_url}" npx prisma migrate deploy --config prisma.config.ts
)

"${postgres_bin}/psql" \
  --host "${postgres_host}" \
  --port "${postgres_port}" \
  --username "${postgres_admin_user}" \
  --dbname "${legacy_database}" \
  --set=ON_ERROR_STOP=1 \
  --file "${repo_api_dir}/test/fixtures/verify-staging-migration.sql"

echo "Native migration verification passed: clean replay, schema drift, PostgreSQL integration and legacy backfill."

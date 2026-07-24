#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
keycloak_home="${VFBIZ_KEYCLOAK_HOME:-${repo_root}/local-data/keycloak/keycloak-26.7.0}"
state_dir="${VFBIZ_KEYCLOAK_STATE_DIR:-${repo_root}/local-data/keycloak/native}"
environment_file="${state_dir}/.env"
server_url="${VFBIZ_KEYCLOAK_SERVER_URL:-http://127.0.0.1:8080}"

if [[ ! -f "${environment_file}" ]]; then
  echo "Missing local Keycloak environment. Run native-bootstrap.sh first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${environment_file}"
set +a

export JAVA_HOME="/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home"
kcadm="${keycloak_home}/bin/kcadm.sh"
"${kcadm}" config credentials \
  --server "${server_url}" \
  --realm master \
  --user "${KC_BOOTSTRAP_ADMIN_USERNAME}" \
  --password "${KC_BOOTSTRAP_ADMIN_PASSWORD}" >/dev/null

smoke_username="vfbiz-identity-bridge-smoke-$(date +%s)-${RANDOM}"
smoke_user_id="$("${kcadm}" create users \
  -r vfbiz-customer \
  -s "username=${smoke_username}" \
  -s "email=${smoke_username}@example.invalid" \
  -s 'firstName=Identity' \
  -s 'lastName=Bridge Smoke' \
  -s 'enabled=true' \
  -s 'emailVerified=true' \
  -i)"
if [[ ! "${smoke_user_id}" =~ ^[0-9a-fA-F-]{36}$ ]]; then
  echo "Could not create the synthetic identity bridge smoke user." >&2
  exit 1
fi
cleanup() {
  "${kcadm}" delete "users/${smoke_user_id}" -r vfbiz-customer >/dev/null 2>&1 \
    || true
}
trap cleanup EXIT

token_response="$(curl --fail --silent --show-error --max-time 5 \
  -X POST \
  "${server_url}/realms/vfbiz-customer/protocol/openid-connect/token" \
  -H 'content-type: application/x-www-form-urlencoded' \
  --data-urlencode grant_type=client_credentials \
  --data-urlencode client_id=vfbiz-customer-identity-bridge \
  --data-urlencode \
    "client_secret=${VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_SECRET}")"
bridge_token="$(jq -er '.access_token' <<<"${token_response}")"

curl --fail --silent --show-error --max-time 5 \
  -H "authorization: Bearer ${bridge_token}" \
  "${server_url}/admin/realms/vfbiz-customer/users/${smoke_user_id}" \
  | jq -e --arg id "${smoke_user_id}" \
    '.id == $id and .emailVerified == true' >/dev/null
curl --fail --silent --show-error --max-time 5 \
  -H "authorization: Bearer ${bridge_token}" \
  "${server_url}/admin/realms/vfbiz-customer/users/${smoke_user_id}/credentials" \
  | jq -e 'type == "array"' >/dev/null
status="$(curl --silent --show-error --max-time 5 \
  -o /dev/null \
  -w '%{http_code}' \
  -X POST \
  -H "authorization: Bearer ${bridge_token}" \
  "${server_url}/admin/realms/vfbiz-customer/users/${smoke_user_id}/logout")"
if [[ "${status}" != "204" ]]; then
  echo "Identity bridge subject logout returned HTTP ${status}." >&2
  exit 1
fi

echo "Customer Identity Bridge read/security/logout smoke test passed."

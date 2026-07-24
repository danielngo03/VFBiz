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

server_info="$("${kcadm}" get serverinfo)"
for theme in vfbiz-customer vfbiz-workforce
do
  jq -e --arg theme "${theme}" '
    any(.themes.login[]?; (.name // .) == $theme) and
    any(.themes.email[]?; (.name // .) == $theme)
  ' <<<"${server_info}" >/dev/null || {
    echo "Keycloak has not loaded ${theme}; restart after installing the JAR." >&2
    exit 1
  }
done

"${kcadm}" update realms/vfbiz-customer \
  -s 'loginTheme=vfbiz-customer' \
  -s 'emailTheme=vfbiz-customer' \
  -s 'internationalizationEnabled=true' \
  -s 'supportedLocales=["vi","en"]' \
  -s 'defaultLocale=vi' \
  -s 'webAuthnPolicyRpEntityName=VFBiz Customer' \
  -s 'webAuthnPolicySignatureAlgorithms=["ES256","RS256"]' \
  -s 'webAuthnPolicyResidentKey=preferred' \
  -s 'webAuthnPolicyUserVerificationRequirement=preferred' \
  -s 'webAuthnPolicyPasswordlessRpEntityName=VFBiz Customer' \
  -s 'webAuthnPolicyPasswordlessSignatureAlgorithms=["ES256","RS256"]' \
  -s 'webAuthnPolicyPasswordlessResidentKey=required' \
  -s 'webAuthnPolicyPasswordlessUserVerificationRequirement=required' \
  -s 'accessTokenLifespan=300' \
  -s 'ssoSessionIdleTimeout=86400' \
  -s 'ssoSessionMaxLifespan=1209600' \
  -s 'clientSessionIdleTimeout=86400' \
  -s 'clientSessionMaxLifespan=1209600' \
  -s 'revokeRefreshToken=true' \
  -s 'refreshTokenMaxReuse=0' >/dev/null
"${kcadm}" update realms/vfbiz-workforce \
  -s 'loginTheme=vfbiz-workforce' \
  -s 'emailTheme=vfbiz-workforce' \
  -s 'internationalizationEnabled=true' \
  -s 'supportedLocales=["vi","en"]' \
  -s 'defaultLocale=vi' \
  -s 'webAuthnPolicyRpEntityName=VFBiz Workforce' \
  -s 'webAuthnPolicySignatureAlgorithms=["ES256","RS256"]' \
  -s 'webAuthnPolicyResidentKey=preferred' \
  -s 'webAuthnPolicyUserVerificationRequirement=required' \
  -s 'webAuthnPolicyPasswordlessRpEntityName=VFBiz Workforce' \
  -s 'webAuthnPolicyPasswordlessSignatureAlgorithms=["ES256","RS256"]' \
  -s 'webAuthnPolicyPasswordlessResidentKey=required' \
  -s 'webAuthnPolicyPasswordlessUserVerificationRequirement=required' \
  -s 'accessTokenLifespan=300' \
  -s 'ssoSessionIdleTimeout=1800' \
  -s 'ssoSessionMaxLifespan=28800' \
  -s 'clientSessionIdleTimeout=1800' \
  -s 'clientSessionMaxLifespan=28800' \
  -s 'revokeRefreshToken=true' \
  -s 'refreshTokenMaxReuse=0' >/dev/null

ensure_required_action() {
  local realm="$1"
  local provider="$2"
  local name="$3"
  local priority="$4"
  local default_action="$5"
  local actions

  actions="$("${kcadm}" get authentication/required-actions -r "${realm}")"
  if ! jq -e --arg provider "${provider}" \
    'any(.[]; .providerId == $provider)' <<<"${actions}" >/dev/null; then
    "${kcadm}" create authentication/register-required-action \
      -r "${realm}" \
      -s "providerId=${provider}" \
      -s "name=${name}" >/dev/null
  fi
  "${kcadm}" update "authentication/required-actions/${provider}" \
    -r "${realm}" \
    -s "name=${name}" \
    -s "enabled=true" \
    -s "defaultAction=${default_action}" \
    -s "priority=${priority}" >/dev/null
}

for realm in vfbiz-customer vfbiz-workforce
do
  ensure_required_action "${realm}" \
    webauthn-register "Webauthn Register" 80 false
  ensure_required_action "${realm}" \
    webauthn-register-passwordless "Webauthn Register Passwordless" 90 false
  ensure_required_action "${realm}" \
    CONFIGURE_RECOVERY_AUTHN_CODES "Recovery Authentication Codes" 130 false
done

customer_bridge="$("${kcadm}" get clients \
  -r vfbiz-customer \
  -q clientId=vfbiz-customer-identity-bridge)"
if [[ "$(jq 'length' <<<"${customer_bridge}")" -eq 0 ]]; then
  "${kcadm}" create clients \
    -r vfbiz-customer \
    -s 'clientId=vfbiz-customer-identity-bridge' \
    -s 'name=VFBiz Customer Identity Bridge' \
    -s 'enabled=true' \
    -s 'publicClient=false' \
    -s 'bearerOnly=false' \
    -s 'standardFlowEnabled=false' \
    -s 'directAccessGrantsEnabled=false' \
    -s 'serviceAccountsEnabled=true' \
    -s "secret=${VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_SECRET}" >/dev/null
  customer_bridge="$("${kcadm}" get clients \
    -r vfbiz-customer \
    -q clientId=vfbiz-customer-identity-bridge)"
fi
customer_bridge_id="$(jq -er '
  if length == 1 then .[0].id else error("customer identity bridge not unique") end
' <<<"${customer_bridge}")"
"${kcadm}" update "clients/${customer_bridge_id}" \
  -r vfbiz-customer \
  -s 'name=VFBiz Customer Identity Bridge' \
  -s 'enabled=true' \
  -s 'publicClient=false' \
  -s 'bearerOnly=false' \
  -s 'standardFlowEnabled=false' \
  -s 'directAccessGrantsEnabled=false' \
  -s 'serviceAccountsEnabled=true' \
  -s "secret=${VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_SECRET}" >/dev/null
"${kcadm}" add-roles \
  -r vfbiz-customer \
  --uusername service-account-vfbiz-customer-identity-bridge \
  --cclientid realm-management \
  --rolename view-users \
  --rolename manage-users >/dev/null

customer_client="$("${kcadm}" get clients \
  -r vfbiz-customer \
  -q clientId=vfbiz-customer-bff)"
customer_client_id="$(jq -er '
  if length == 1 then .[0].id else error("customer BFF client not unique") end
' <<<"${customer_client}")"
"${kcadm}" update "clients/${customer_client_id}" \
  -r vfbiz-customer \
  -s 'name=VFBiz Customer Portal BFF' \
  -s 'redirectUris=["http://127.0.0.1:8000/auth/customer/callback","http://localhost:3001/api/auth/callback"]' \
  -s 'webOrigins=["http://127.0.0.1:8000","http://127.0.0.1:5173","http://localhost:3001"]' \
  -s 'attributes={"pkce.code.challenge.method":"S256","backchannel.logout.url":"http://localhost:3001/api/auth/backchannel-logout","backchannel.logout.session.required":"true"}' >/dev/null

workforce_client="$("${kcadm}" get clients \
  -r vfbiz-workforce \
  -q clientId=vfbiz-workforce-bff)"
workforce_client_id="$(jq -er '
  if length == 1 then .[0].id else error("workforce BFF client not unique") end
' <<<"${workforce_client}")"
"${kcadm}" update "clients/${workforce_client_id}" \
  -r vfbiz-workforce \
  -s 'name=VFBiz Workforce Portal BFF' \
  -s 'redirectUris=["http://localhost:3002/api/auth/callback"]' \
  -s 'webOrigins=["http://localhost:3002"]' >/dev/null

for role in \
  vehicle-data-reviewer \
  commercial-data-operator \
  commercial-data-reviewer
do
  if ! "${kcadm}" get "roles/${role}" -r vfbiz-workforce >/dev/null 2>&1; then
    "${kcadm}" create roles -r vfbiz-workforce -s "name=${role}" >/dev/null
  fi
done

basic_scope="$("${kcadm}" get client-scopes \
  -r vfbiz-workforce \
  -q name=basic)"
basic_scope_id="$(jq -er '
  [.[] | select(.name == "basic")] |
  if length == 1 then .[0].id else error("basic scope not unique") end
' \
  <<<"${basic_scope}")"
mappers="$("${kcadm}" get \
  "client-scopes/${basic_scope_id}/protocol-mappers/models" \
  -r vfbiz-workforce)"

if ! jq -e '
  any(.[]; .protocolMapper == "oidc-amr-mapper" and
    .config["access.token.claim"] == "true")
' <<<"${mappers}" >/dev/null; then
  jq -n '{
    name: "authentication methods",
    protocol: "openid-connect",
    protocolMapper: "oidc-amr-mapper",
    consentRequired: false,
    config: {
      "id.token.claim": "true",
      "access.token.claim": "true",
      "lightweight.claim": "false"
    }
  }' | "${kcadm}" create \
    "client-scopes/${basic_scope_id}/protocol-mappers/models" \
    -r vfbiz-workforce \
    -f - >/dev/null
fi

echo "Local identity themes, locale policy, customer BFF/session policy, identity bridge, workforce roles and AMR mapper are reconciled."

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

customer_discovery="$(mktemp)"
workforce_discovery="$(mktemp)"
customer_jwks="$(mktemp)"
trap 'rm -f "${customer_discovery}" "${workforce_discovery}" "${customer_jwks}"' EXIT

curl --fail --silent --show-error \
  "${server_url}/realms/vfbiz-customer/.well-known/openid-configuration" \
  >"${customer_discovery}"
curl --fail --silent --show-error \
  "${server_url}/realms/vfbiz-workforce/.well-known/openid-configuration" \
  >"${workforce_discovery}"
curl --fail --silent --show-error \
  "${server_url}/realms/vfbiz-customer/protocol/openid-connect/certs" \
  >"${customer_jwks}"

jq -e --arg issuer "${server_url}/realms/vfbiz-customer" \
  '.issuer == $issuer and
   (.authorization_endpoint | endswith("/protocol/openid-connect/auth")) and
   (.token_endpoint | endswith("/protocol/openid-connect/token")) and
   (.jwks_uri | endswith("/protocol/openid-connect/certs"))' \
  "${customer_discovery}" >/dev/null
jq -e --arg issuer "${server_url}/realms/vfbiz-workforce" \
  '.issuer == $issuer' "${workforce_discovery}" >/dev/null
jq -e '[.keys[] | select(.use == "sig" and .alg == "RS256")] | length > 0' \
  "${customer_jwks}" >/dev/null

"${kcadm}" config credentials \
  --server "${server_url}" \
  --realm master \
  --user "${KC_BOOTSTRAP_ADMIN_USERNAME}" \
  --password "${KC_BOOTSTRAP_ADMIN_PASSWORD}" >/dev/null

customer_realm="$("${kcadm}" get realms/vfbiz-customer)"
workforce_realm="$("${kcadm}" get realms/vfbiz-workforce)"
customer_client="$("${kcadm}" get clients \
  -r vfbiz-customer \
  -q clientId=vfbiz-customer-bff)"
workforce_client="$("${kcadm}" get clients \
  -r vfbiz-workforce \
  -q clientId=vfbiz-workforce-bff)"
customer_bridge="$("${kcadm}" get clients \
  -r vfbiz-customer \
  -q clientId=vfbiz-customer-identity-bridge)"
server_info="$("${kcadm}" get serverinfo)"

for required_theme in vfbiz-customer vfbiz-workforce
do
  jq -e --arg theme "${required_theme}" '
    any(.themes.login[]?; (.name // .) == $theme) and
    any(.themes.email[]?; (.name // .) == $theme)
  ' <<<"${server_info}" >/dev/null
done

jq -e '
  .loginTheme == "vfbiz-customer" and
  .emailTheme == "vfbiz-customer" and
  .internationalizationEnabled == true and
  .defaultLocale == "vi" and
  (.supportedLocales | sort) == ["en", "vi"] and
  .registrationAllowed == true and
  .webAuthnPolicyRpEntityName == "VFBiz Customer" and
  .webAuthnPolicyResidentKey == "preferred" and
  .webAuthnPolicyUserVerificationRequirement == "preferred" and
  .webAuthnPolicyPasswordlessResidentKey == "required" and
  .webAuthnPolicyPasswordlessUserVerificationRequirement == "required" and
  .accessTokenLifespan == 300 and
  .ssoSessionIdleTimeout == 86400 and
  .ssoSessionMaxLifespan == 1209600 and
  .revokeRefreshToken == true and
  .refreshTokenMaxReuse == 0
' <<<"${customer_realm}" >/dev/null
jq -e '
  .loginTheme == "vfbiz-workforce" and
  .emailTheme == "vfbiz-workforce" and
  .internationalizationEnabled == true and
  .defaultLocale == "vi" and
  (.supportedLocales | sort) == ["en", "vi"] and
  .registrationAllowed == false and
  .webAuthnPolicyRpEntityName == "VFBiz Workforce" and
  .webAuthnPolicyResidentKey == "preferred" and
  .webAuthnPolicyUserVerificationRequirement == "required" and
  .webAuthnPolicyPasswordlessResidentKey == "required" and
  .webAuthnPolicyPasswordlessUserVerificationRequirement == "required" and
  .accessTokenLifespan == 300 and
  .ssoSessionIdleTimeout == 1800 and
  .ssoSessionMaxLifespan == 28800 and
  .revokeRefreshToken == true and
  .refreshTokenMaxReuse == 0
' <<<"${workforce_realm}" >/dev/null

for realm in vfbiz-customer vfbiz-workforce
do
  required_actions="$("${kcadm}" get authentication/required-actions -r "${realm}")"
  for provider in \
    CONFIGURE_TOTP \
    webauthn-register \
    webauthn-register-passwordless \
    CONFIGURE_RECOVERY_AUTHN_CODES
  do
    jq -e --arg provider "${provider}" '
      any(.[]; .providerId == $provider and .enabled == true)
    ' <<<"${required_actions}" >/dev/null
  done
done

jq -e '
  length == 1 and
  .[0].publicClient == false and
  .[0].standardFlowEnabled == true and
  .[0].directAccessGrantsEnabled == false and
  .[0].attributes["pkce.code.challenge.method"] == "S256" and
  .[0].attributes["backchannel.logout.session.required"] == "true" and
  .[0].attributes["backchannel.logout.url"] == "http://localhost:3001/api/auth/backchannel-logout" and
  (.[0].redirectUris | index("http://127.0.0.1:8000/auth/customer/callback")) != null and
  (.[0].redirectUris | index("http://localhost:3001/api/auth/callback")) != null
' <<<"${customer_client}" >/dev/null

jq -e '
  length == 1 and
  .[0].publicClient == false and
  .[0].standardFlowEnabled == true and
  .[0].directAccessGrantsEnabled == false and
  .[0].attributes["pkce.code.challenge.method"] == "S256" and
  (.[0].redirectUris | index("http://localhost:3002/api/auth/callback")) != null
' <<<"${workforce_client}" >/dev/null

jq -e '
  length == 1 and
  .[0].publicClient == false and
  .[0].standardFlowEnabled == false and
  .[0].directAccessGrantsEnabled == false and
  .[0].serviceAccountsEnabled == true
' <<<"${customer_bridge}" >/dev/null

customer_bridge_id="$(jq -er '.[0].id' <<<"${customer_bridge}")"
customer_bridge_service_account="$("${kcadm}" get \
  "clients/${customer_bridge_id}/service-account-user" \
  -r vfbiz-customer)"
customer_bridge_username="$(jq -er '.username' \
  <<<"${customer_bridge_service_account}")"
realm_management="$("${kcadm}" get clients \
  -r vfbiz-customer \
  -q clientId=realm-management)"
realm_management_id="$(jq -er '
  if length == 1 then .[0].id else error("realm-management client not unique") end
' <<<"${realm_management}")"
customer_bridge_roles="$("${kcadm}" get-roles \
  -r vfbiz-customer \
  --uusername "${customer_bridge_username}" \
  --cid "${realm_management_id}" \
  --effective)"
for required_bridge_role in view-users manage-users
do
  jq -e --arg role "${required_bridge_role}" \
    'any(.[]; .name == $role)' <<<"${customer_bridge_roles}" >/dev/null
done

for required_scope in \
  basic profile email vfbiz-customer-audience \
  profile:read profile:write consent:read consent:write \
  session:read session:revoke garage:read garage:write \
  data-request:create data-request:read
do
  jq -e --arg scope "${required_scope}" \
    '.[0].defaultClientScopes | index($scope) != null' \
    <<<"${customer_client}" >/dev/null
done

for required_role in \
  vehicle-data-operator vehicle-data-reviewer \
  commercial-data-operator commercial-data-reviewer
do
  "${kcadm}" get "roles/${required_role}" \
    -r vfbiz-workforce >/dev/null
done

workforce_basic_scope="$("${kcadm}" get client-scopes \
  -r vfbiz-workforce \
  -q name=basic)"
workforce_basic_scope_id="$(jq -er '
  [.[] | select(.name == "basic")] |
  if length == 1 then .[0].id else error("workforce basic scope not unique") end
' <<<"${workforce_basic_scope}")"
workforce_mappers="$("${kcadm}" get \
  "client-scopes/${workforce_basic_scope_id}/protocol-mappers/models" \
  -r vfbiz-workforce)"
jq -e '
  any(.[]; .protocolMapper == "oidc-amr-mapper" and
    .config["access.token.claim"] == "true")
' <<<"${workforce_mappers}" >/dev/null

echo "Keycloak themes, localization, discovery, JWKS, PKCE, bounded sessions, token rotation, back-channel logout, scopes, identity bridge, workforce roles and AMR are valid."

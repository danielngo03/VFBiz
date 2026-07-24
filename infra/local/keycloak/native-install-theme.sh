#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
keycloak_home="${VFBIZ_KEYCLOAK_HOME:-${repo_root}/local-data/keycloak/keycloak-26.7.0}"
state_dir="${VFBIZ_KEYCLOAK_STATE_DIR:-${repo_root}/local-data/keycloak/native}"
pid_file="${state_dir}/keycloak.pid"
providers_dir="${keycloak_home}/providers"

npm run identity-theme:build --prefix "${repo_root}" >/dev/null
source_jar="$(
  find "${repo_root}/apps/identity-theme/dist" \
    -maxdepth 1 \
    -type f \
    -name 'vfbiz-identity-theme-*-kc26.7.0.jar' \
    -print
)"
if [[ -z "${source_jar}" ]] || [[ "$(wc -l <<<"${source_jar}" | tr -d ' ')" -ne 1 ]]; then
  echo "Expected exactly one Keycloak 26.7.0 identity theme JAR." >&2
  exit 1
fi

mkdir -p "${providers_dir}" "${state_dir}"
target_jar="${providers_dir}/$(basename "${source_jar}")"
source_checksum="$(shasum -a 256 "${source_jar}" | awk '{print $1}')"
target_checksum=""
if [[ -f "${target_jar}" ]]; then
  target_checksum="$(shasum -a 256 "${target_jar}" | awk '{print $1}')"
fi

if [[ "${source_checksum}" == "${target_checksum}" ]]; then
  echo "Identity theme ${source_checksum} is already installed."
  exit 0
fi

if [[ -f "${pid_file}" ]] && kill -0 "$(cat "${pid_file}")" 2>/dev/null; then
  echo "Keycloak is running with a different theme artifact." >&2
  echo "Run native-stop.sh, then native-start.sh to install it safely." >&2
  exit 1
fi

temporary="${target_jar}.tmp.$$"
cp "${source_jar}" "${temporary}"
chmod 0644 "${temporary}"
mv "${temporary}" "${target_jar}"

for legacy_jar in "${providers_dir}"/vfbiz-identity-theme-*-kc26.7.0.jar; do
  [[ -e "${legacy_jar}" ]] || continue
  [[ "${legacy_jar}" == "${target_jar}" ]] || rm -f "${legacy_jar}"
done

printf '%s  %s\n' "${source_checksum}" "$(basename "${target_jar}")" \
  >"${state_dir}/identity-theme.sha256"
echo "Installed $(basename "${target_jar}") (${source_checksum})."

#!/usr/bin/env bash
set -euo pipefail

image="${1:?Usage: verify-image.sh <digest-pinned-image>}"
case "${image}" in
  *@sha256:*) ;;
  *)
    echo "Keycloak image must be referenced by digest." >&2
    exit 1
    ;;
esac

docker run --rm --entrypoint /bin/sh "${image}" -ec '
  test -s /opt/keycloak/providers/vfbiz-identity-theme.jar
  /opt/keycloak/bin/kc.sh show-config >/dev/null
'

echo "Keycloak image contains the reviewed VFBiz identity themes."

# Keycloak runtime image

This directory packages the reviewed Identity Theme into an immutable Keycloak
image. Build from the repository root after `npm run identity-theme:build`.

```bash
docker build \
  --file infra/keycloak/Containerfile \
  --build-arg KEYCLOAK_IMAGE=quay.io/keycloak/keycloak@sha256:<reviewed-digest> \
  --tag vfbiz-keycloak:<release> \
  .
```

The base image must be digest-pinned. Production never bind-mounts providers or
theme source. Realm configuration and secrets remain environment concerns and
are not baked into this image.

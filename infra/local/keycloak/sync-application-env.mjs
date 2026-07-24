#!/usr/bin/env node
import { randomBytes } from "node:crypto";
import { chmod, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = resolve(
  fileURLToPath(new URL("../../..", import.meta.url)),
);
const keycloakEnvironmentPath = resolve(
  repositoryRoot,
  "local-data/keycloak/native/.env",
);

function parseEnvironment(source) {
  return new Map(
    source
      .split(/\r?\n/u)
      .filter((line) => line.trim() !== "" && !line.trimStart().startsWith("#"))
      .map((line) => {
        const index = line.indexOf("=");
        return [line.slice(0, index), line.slice(index + 1)];
      }),
  );
}

function setValue(source, key, value) {
  const line = `${key}=${value}`;
  const expression = new RegExp(`^${key}=.*$`, "mu");
  if (expression.test(source)) return source.replace(expression, line);
  return `${source.trimEnd()}\n${line}\n`;
}

async function updateFromTemplate(path, template, values) {
  let source;
  try {
    source = await readFile(path, "utf8");
  } catch {
    source = await readFile(template, "utf8");
  }
  for (const [key, value] of Object.entries(values)) {
    source = setValue(source, key, value);
  }
  await writeFile(path, source, { encoding: "utf8", mode: 0o600 });
  await chmod(path, 0o600);
}

const keycloak = parseEnvironment(
  await readFile(keycloakEnvironmentPath, "utf8"),
);
for (const key of [
  "VFBIZ_CUSTOMER_OIDC_CLIENT_SECRET",
  "VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_SECRET",
  "VFBIZ_WORKFORCE_OIDC_CLIENT_SECRET",
]) {
  if (!keycloak.get(key)) {
    throw new Error(`Missing ${key}; run native-bootstrap.sh first.`);
  }
}

await updateFromTemplate(
  resolve(repositoryRoot, "backend/api/.env"),
  resolve(repositoryRoot, "backend/api/.env.example"),
  {
    VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_ID: "vfbiz-customer-identity-bridge",
    VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_SECRET: keycloak.get(
      "VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_SECRET",
    ),
    VFBIZ_CUSTOMER_OIDC_CLIENT_SECRET: keycloak.get(
      "VFBIZ_CUSTOMER_OIDC_CLIENT_SECRET",
    ),
  },
);

const customerPortalEnvironmentPath = resolve(
  repositoryRoot,
  "apps/customer-portal/.env.local",
);
let customerPortalVaultKey = randomBytes(32).toString("base64");
try {
  const existingCustomerPortalEnvironment = parseEnvironment(
    await readFile(customerPortalEnvironmentPath, "utf8"),
  );
  const existingKey = existingCustomerPortalEnvironment.get(
    "CUSTOMER_TOKEN_VAULT_KEY",
  );
  if (existingKey && !existingKey.startsWith("replace-with-")) {
    customerPortalVaultKey = existingKey;
  }
} catch {
  // The generated key below initializes a new local-only token vault.
}
await updateFromTemplate(
  customerPortalEnvironmentPath,
  resolve(repositoryRoot, "apps/customer-portal/.env.example"),
  {
    CUSTOMER_OIDC_CLIENT_SECRET: keycloak.get(
      "VFBIZ_CUSTOMER_OIDC_CLIENT_SECRET",
    ),
    CUSTOMER_TOKEN_VAULT_KEY: customerPortalVaultKey,
  },
);

const portalEnvironmentPath = resolve(
  repositoryRoot,
  "apps/workforce-portal/.env.local",
);
let portalVaultKey = randomBytes(32).toString("base64");
try {
  const existingPortalEnvironment = parseEnvironment(
    await readFile(portalEnvironmentPath, "utf8"),
  );
  const existingKey = existingPortalEnvironment.get(
    "WORKFORCE_TOKEN_VAULT_KEY",
  );
  if (existingKey && !existingKey.startsWith("replace-with-")) {
    portalVaultKey = existingKey;
  }
} catch {
  // The generated key below initializes a new local-only token vault.
}
await updateFromTemplate(
  portalEnvironmentPath,
  resolve(repositoryRoot, "apps/workforce-portal/.env.example"),
  {
    WORKFORCE_OIDC_CLIENT_SECRET: keycloak.get(
      "VFBIZ_WORKFORCE_OIDC_CLIENT_SECRET",
    ),
    WORKFORCE_SESSION_IDLE_TIMEOUT_SECONDS: "1800",
    WORKFORCE_TOKEN_VAULT_KEY: portalVaultKey,
  },
);

console.log(
  "Local API, Customer Portal and Workforce Portal environments now reference the reconciled Keycloak clients.",
);

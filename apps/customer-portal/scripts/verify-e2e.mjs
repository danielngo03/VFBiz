import { spawn } from "node:child_process";

const required = ["CUSTOMER_E2E_EMAIL", "CUSTOMER_E2E_PASSWORD"];
const missing = required.filter((name) => !process.env[name]?.trim());

if (missing.length > 0) {
  console.error(
    `Customer Portal E2E is required but missing: ${missing.join(", ")}`,
  );
  process.exit(2);
}

const executable = process.platform === "win32" ? "npx.cmd" : "npx";
const child = spawn(
  executable,
  ["playwright", "test", "--config", "playwright.config.ts"],
  {
    cwd: new URL("..", import.meta.url),
    env: {
      ...process.env,
      CUSTOMER_E2E_ENABLED: "true",
      CUSTOMER_E2E_REQUIRED: "true",
    },
    stdio: "inherit",
  },
);

child.on("error", (error) => {
  console.error(`Unable to start required Customer Portal E2E: ${error.message}`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal !== null) {
    console.error(`Customer Portal E2E terminated by ${signal}.`);
    process.exit(1);
  }
  process.exit(code ?? 1);
});

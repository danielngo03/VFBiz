import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/component/**/*.spec.ts", "tests/component/**/*.spec.tsx"],
    setupFiles: ["./tests/support/component-setup.ts"],
  },
});

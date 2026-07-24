import {fileURLToPath} from 'node:url';
import {defineConfig} from 'vitest/config';

export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    exclude: ['tests/integration/**', 'tests/e2e/**'],
    include: [
      'tests/unit/**/*.spec.ts',
      'tests/component/**/*.spec.tsx',
    ],
    setupFiles: ['./tests/support/setup.ts'],
  },
});

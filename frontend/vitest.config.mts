import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    // Playwright drives whole pages against a running app; these run against the
    // module graph. Keeping them apart stops `vitest` trying to execute the
    // browser suite in jsdom, where it cannot work.
    include: ["src/**/*.test.{ts,tsx}"],
  },
});

import { defineConfig } from "vitest/config";
import path from "path";

// Frontend tests: the visual editor's round trip, run in a simulated
// browser (jsdom) -- ProseMirror needs a DOM to build its document.
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
    testTimeout: 20000,
  },
});

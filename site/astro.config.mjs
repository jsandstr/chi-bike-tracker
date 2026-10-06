import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://jsandstr.github.io",
  base: "/chi-bike-tracker",
  vite: {
    // Pages import generated data from ../data/processed.
    server: { fs: { allow: [".."] } },
    // MapLibre starts its worker as an ES module.
    worker: { format: "es" },
  },
});

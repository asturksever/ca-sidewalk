import { defineConfig } from 'vite';

// GitHub Pages serves the site at /ca-sidewalk/; CI sets GH_PAGES_BASE.
export default defineConfig({
  base: process.env.GH_PAGES_BASE ?? '/',
});

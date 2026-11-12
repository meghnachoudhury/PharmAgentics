// Build config for running this UI outside Figma Make (local Vite, container image).
// vite.config.ts stays the Figma Make config; it imports .figma/make/site.json, which
// only exists inside Figma Make. This file fills the figma:* placeholders in index.html.
import { defineConfig, type Plugin } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "node:path"

function standaloneHtml(): Plugin {
  return {
    name: "pharmagentics-standalone-html",
    transformIndexHtml(html) {
      return html
        .replace("<!-- figma:lang -->", "en")
        .replace("<!-- figma:title -->", "PharmAgentics")
    },
  }
}

export default defineConfig({
  base: "/",
  plugins: [react(), tailwindcss(), standaloneHtml()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    port: 5173,
    // Local dev: forward API calls to `uv run uvicorn pharmagentics.api.app:app` on :8000.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
})

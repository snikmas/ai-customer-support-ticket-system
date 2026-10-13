import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// scripts/verify_release.py sets this so a release check never loads a
// developer's private `.env`/`.env.local` values into the frontend bundle.
const disableEnvFiles =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process
    ?.env?.VITE_VERIFY_DISABLE_ENV_FILES === "1";

export default defineConfig({
  plugins: [react()],
  ...(disableEnvFiles ? { envDir: false as const } : {}),
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});

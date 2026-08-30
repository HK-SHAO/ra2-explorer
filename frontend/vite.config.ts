import { execFileSync } from "node:child_process";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

function gitValue(args: string[]) {
  try {
    return execFileSync("git", args, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const buildCommit = env.VITE_RA2EXP_BUILD_COMMIT || gitValue(["rev-parse", "HEAD"]);
  const buildTag = env.VITE_RA2EXP_BUILD_TAG || gitValue(["describe", "--tags", "--exact-match", "--match", "v*", "HEAD"]);
  const buildTime = env.VITE_RA2EXP_BUILD_TIME || gitValue(["show", "-s", "--format=%cI", "HEAD"]);
  return {
    base: env.RA2EXP_PUBLIC_BASE || "/",
    plugins: [react()],
    define: {
      "import.meta.env.VITE_RA2EXP_BUILD_COMMIT": JSON.stringify(buildCommit),
      "import.meta.env.VITE_RA2EXP_BUILD_TAG": JSON.stringify(buildTag),
      "import.meta.env.VITE_RA2EXP_BUILD_TIME": JSON.stringify(buildTime),
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            const normalized = id.replaceAll("\\", "/");
            if (normalized.endsWith("/three/build/three.core.js")) return "three-core";
            if (normalized.endsWith("/three/build/three.module.js")) return "three-renderer";
          },
        },
      },
    },
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: {
        "/api": "http://127.0.0.1:46120",
      },
    },
  };
});

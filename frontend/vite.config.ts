import { execFileSync } from "node:child_process";
import { defineConfig, loadEnv, type HtmlTagDescriptor, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

function gitValue(args: string[]) {
  try {
    return execFileSync("git", args, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

export default defineConfig(({ mode }) => {
  // Vite's loadEnv() only reads env files. Preserve the documented precedence
  // of variables supplied by the caller/CI over values from .env files.
  const env = { ...loadEnv(mode, ".", ""), ...process.env };
  const buildCommit = env.VITE_RA2EXP_BUILD_COMMIT || gitValue(["rev-parse", "HEAD"]);
  const buildTag = env.VITE_RA2EXP_BUILD_TAG || gitValue(["describe", "--tags", "--exact-match", "--match", "v*", "HEAD"]);
  const buildTime = env.VITE_RA2EXP_BUILD_TIME || gitValue(["show", "-s", "--format=%cI", "HEAD"]);
  const stableTag = env.VITE_RA2EXP_STABLE_TAG
    || gitValue(["tag", "--list", "v*", "--sort=-v:refname"]).split(/\r?\n/, 1)[0]
    || "";
  const [stableBehind = "", stableAhead = ""] = stableTag
    ? gitValue(["rev-list", "--left-right", "--count", `${stableTag}...HEAD`]).split(/\s+/)
    : [];
  const repositoryUrl = (env.VITE_RA2EXP_REPOSITORY_URL || "https://github.com/HK-SHAO/ra2-explorer").replace(/\/$/, "");
  const publicBase = env.RA2EXP_PUBLIC_BASE || "/";
  const normalizedBase = publicBase.endsWith("/") ? publicBase : `${publicBase}/`;
  // Bust cached data JSONs on every local rebuild; deploys set their own stamp.
  const buildStamp = Date.now().toString(36);
  const browserStateVersion = env.VITE_RA2EXP_BROWSER_STATE_VERSION
    || [buildCommit, buildTag].filter(Boolean).concat(buildStamp).join(".")
    || `dev-${buildStamp}`;
  const preloadPagesAssets = {
    name: "preload-pages-startup-assets",
    transformIndexHtml() {
      if (mode !== "pages") return [];
      const snapshotUrl = (path: string) => {
        const version = browserStateVersion ? `?v=${encodeURIComponent(browserStateVersion)}` : "";
        return `${normalizedBase}data/${path}${version}`;
      };
      const links: HtmlTagDescriptor[] = [
        {
          tag: "link",
          attrs: { rel: "preload", as: "fetch", crossorigin: "anonymous", href: snapshotUrl("manifest.json") },
          injectTo: "head-prepend" as const,
        },
        {
          tag: "link",
          attrs: { rel: "preload", as: "fetch", crossorigin: "anonymous", href: snapshotUrl("catalog/entities.zh-CN.json") },
          injectTo: "head-prepend" as const,
        },
      ];
      return links;
    },
  } satisfies Plugin;
  return {
    base: publicBase,
    plugins: [react(), preloadPagesAssets],
    define: {
      "import.meta.env.VITE_RA2EXP_BUILD_COMMIT": JSON.stringify(buildCommit),
      "import.meta.env.VITE_RA2EXP_BUILD_TAG": JSON.stringify(buildTag),
      "import.meta.env.VITE_RA2EXP_BUILD_TIME": JSON.stringify(buildTime),
      "import.meta.env.VITE_RA2EXP_STABLE_TAG": JSON.stringify(stableTag),
      "import.meta.env.VITE_RA2EXP_STABLE_AHEAD": JSON.stringify(env.VITE_RA2EXP_STABLE_AHEAD || stableAhead),
      "import.meta.env.VITE_RA2EXP_STABLE_BEHIND": JSON.stringify(env.VITE_RA2EXP_STABLE_BEHIND || stableBehind),
      "import.meta.env.VITE_RA2EXP_REPOSITORY_URL": JSON.stringify(repositoryUrl),
      "import.meta.env.VITE_RA2EXP_BROWSER_STATE_VERSION": JSON.stringify(browserStateVersion),
    },
    build: {
      outDir: mode === "pages" ? "dist-pages" : "dist",
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

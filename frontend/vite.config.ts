import { defineConfig, Plugin } from "vite";
import react from "@vitejs/plugin-react";
import fs from "fs";
import path from "path";

function pwaPrecachePlugin(): Plugin {
  return {
    name: "pwa-precache-generator",
    apply: "build",
    writeBundle(options, bundle) {
      const outDir = options.dir || "dist";
      const assets: string[] = [
        "/",
        "/index.html",
        "/manifest.webmanifest",
        "/favicon.svg",
        "/icons/icon-192.png",
        "/icons/icon-512.png",
        "/icons/icon-maskable-512.png",
        "/audio/alerts/en/posture_moderate.mp3",
        "/audio/alerts/en/posture_high.mp3",
        "/audio/alerts/en/alertness_moderate.mp3",
        "/audio/alerts/en/alertness_high.mp3",
        "/audio/alerts/ta/posture_moderate.mp3",
        "/audio/alerts/ta/posture_high.mp3",
        "/audio/alerts/ta/alertness_moderate.mp3",
        "/audio/alerts/ta/alertness_high.mp3"
      ];

      for (const fileName of Object.keys(bundle)) {
        if (fileName.startsWith("assets/")) {
          assets.push(`/${fileName}`);
        }
      }

      const swContent = `// VisionGuard Native PWA Service Worker (Auto-generated exact precache)
const CACHE_NAME = "visionguard-shell-v1";
const PRECACHE_ASSETS = ${JSON.stringify(assets, null, 2)};

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Strictly NETWORK-ONLY for all APIs, Supabase, WebSockets, preview, and mutations
  if (
    event.request.method !== "GET" ||
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/health") ||
    url.hostname.includes("supabase.co")
  ) {
    return;
  }

  // Navigation request fallback: serve cached index.html for client-side routing
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() => caches.match("/index.html"))
    );
    return;
  }

  // Static assets: Cache-first, network fallback
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(event.request).then((response) => {
        if (
          response &&
          response.status === 200 &&
          url.origin === self.location.origin &&
          (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/audio/"))
        ) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      });
    })
  );
});
`;

      fs.writeFileSync(path.join(outDir, "sw.js"), swContent, "utf-8");
    }
  };
}

export default defineConfig({
  plugins: [react(), pwaPrecachePlugin()],
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (id.includes("@supabase")) {
              return "supabase";
            }
            if (id.includes("react")) {
              return "react-vendor";
            }
            return "vendor";
          }
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        ws: true,
      },
      "/health": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});

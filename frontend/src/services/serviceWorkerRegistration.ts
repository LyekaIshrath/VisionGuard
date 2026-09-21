export function registerServiceWorker(onUpdate?: () => void) {
  if ("serviceWorker" in navigator) {
    if (import.meta.env.PROD) {
      window.addEventListener("load", () => {
        navigator.serviceWorker
          .register("/sw.js")
          .then((registration) => {
            registration.addEventListener("updatefound", () => {
              const installingWorker = registration.installing;
              if (!installingWorker) return;
              installingWorker.addEventListener("statechange", () => {
                if (installingWorker.state === "installed") {
                  if (navigator.serviceWorker.controller) {
                    if (onUpdate) onUpdate();
                  }
                }
              });
            });
          })
          .catch((error) => {
            console.warn("VisionGuard Service Worker registration failed:", error);
          });
      });
    } else {
      // In development, unconditionally unregister existing workers and clear cache to avoid stale runtime assets
      navigator.serviceWorker.getRegistrations().then((registrations) => {
        for (const reg of registrations) {
          reg.unregister();
        }
      });
      if ("caches" in window) {
        caches.keys().then((names) => {
          for (const name of names) {
            caches.delete(name);
          }
        });
      }
    }
  }
}

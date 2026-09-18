export function registerServiceWorker(onUpdate?: () => void) {
  if ("serviceWorker" in navigator && import.meta.env.PROD) {
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
                  // Update available, trigger callback
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
  }
}

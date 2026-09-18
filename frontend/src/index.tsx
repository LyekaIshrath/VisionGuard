import "./index.css";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { registerServiceWorker } from "./services/serviceWorkerRegistration";

const container = document.getElementById("root") as HTMLElement | null;
if (!container) {
  throw new Error("Root element not found");
}

ReactDOM.createRoot(container).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// Register service worker in production
registerServiceWorker(() => {
  // Dispatch custom event if service worker has a pending update
  window.dispatchEvent(new CustomEvent("visionguard-sw-update"));
});

import "./index.css";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

const container = document.getElementById("root") as HTMLElement | null;
if (!container) {
  throw new Error("Root element not found");
}

ReactDOM.createRoot(container).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
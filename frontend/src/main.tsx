import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import "highlight.js/styles/github-dark.css";
import App from "./App.tsx";
import { applyTheme, getPreferredTheme } from "@/lib/theme";
import { registerServiceWorker } from "@/lib/offlineCache";
import { applyReaderPrefs } from "@/lib/readerPrefs";

applyTheme(getPreferredTheme());
applyReaderPrefs();
registerServiceWorker();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

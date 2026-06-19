import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import NotchApp from "./notch/NotchApp";
import "./index.css";
import "./notch/NotchApp.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <NotchApp />
  </StrictMode>
);

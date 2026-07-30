import { useState } from "react";

import Dashboard from "./pages/Dashboard";
import LogViewer from "./pages/LogViewer";

type Tab = "dashboard" | "logs";

export default function App() {
  const [tab, setTab] = useState<Tab>("dashboard");

  return (
    <div className="app">
      <nav className="app__nav">
        <span className="app__brand">LogMon</span>
        <button
          type="button"
          className={tab === "dashboard" ? "tab tab--active" : "tab"}
          onClick={() => setTab("dashboard")}
        >
          Dashboard
        </button>
        <button
          type="button"
          className={tab === "logs" ? "tab tab--active" : "tab"}
          onClick={() => setTab("logs")}
        >
          Visualizar logs
        </button>
      </nav>

      <main className="app__main">
        {tab === "dashboard" ? <Dashboard /> : <LogViewer />}
      </main>
    </div>
  );
}

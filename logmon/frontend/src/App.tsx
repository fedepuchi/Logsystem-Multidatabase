import { useState } from "react";

import AdminKeyBar from "./components/AdminKeyBar";
import Dashboard from "./pages/Dashboard";
import LogViewer from "./pages/LogViewer";

type Tab = "dashboard" | "logs";

export default function App() {
  const [tab, setTab] = useState<Tab>("dashboard");

  // Cambiar la clave de admin cambia quién es el que pregunta: se remonta la
  // página para que vuelva a pedir todo con la credencial nueva.
  const [authVersion, setAuthVersion] = useState(0);

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

        <AdminKeyBar onChanged={() => setAuthVersion((version) => version + 1)} />
      </nav>

      <main className="app__main" key={authVersion}>
        {tab === "dashboard" ? <Dashboard /> : <LogViewer />}
      </main>
    </div>
  );
}

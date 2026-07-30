import { useCallback, useEffect, useState } from "react";

import ConnectionForm from "../components/ConnectionForm";
import SourceAssign from "../components/SourceAssign";
import SwitchControl from "../components/SwitchControl";
import {
  ApiError,
  connectionsApi,
  sourcesApi,
  type Connection,
  type Source,
} from "../api/client";

type Feedback = { kind: "ok" | "error"; message: string };

export default function Dashboard() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [conns, srcs] = await Promise.all([connectionsApi.list(), sourcesApi.list()]);
      setConnections(conns);
      setSources(srcs);
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "No se pudieron cargar los datos";
      setFeedback({ kind: "error", message });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function reportError(message: string) {
    setFeedback({ kind: "error", message });
  }

  async function handleTest(connectionId: string) {
    setFeedback(null);
    try {
      const result = await connectionsApi.test(connectionId);
      setFeedback({ kind: result.success ? "ok" : "error", message: result.message });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "El test de conexión falló";
      setFeedback({ kind: "error", message });
    }
  }

  async function handleDelete(connectionId: string) {
    setFeedback(null);
    try {
      await connectionsApi.remove(connectionId);
      await load();
      setFeedback({ kind: "ok", message: `Conexión ${connectionId} eliminada` });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "No se pudo eliminar la conexión";
      setFeedback({ kind: "error", message });
    }
  }

  function handleSwitched(updated: Source) {
    setSources((prev) =>
      prev.map((source) => (source.name === updated.name ? updated : source)),
    );
    setFeedback({
      kind: "ok",
      message: `${updated.name} ahora escribe en ${updated.connection_id}`,
    });
  }

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <h1>Panel de administración</h1>
        <button type="button" onClick={() => void load()} disabled={loading}>
          {loading ? "Cargando..." : "Refrescar"}
        </button>
      </header>

      {feedback && (
        <p className={`feedback feedback--${feedback.kind}`} role="status">
          {feedback.message}
        </p>
      )}

      <section className="dashboard__section">
        <ConnectionForm onCreated={() => void load()} />
      </section>

      <section className="dashboard__section">
        <h2>Conexiones</h2>
        {connections.length === 0 ? (
          <p>No hay conexiones registradas.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Nombre</th>
                <th>Motor</th>
                <th>Host</th>
                <th>Puerto</th>
                <th>Base</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {connections.map((connection) => (
                <tr key={connection.id}>
                  <td>{connection.id}</td>
                  <td>{connection.name}</td>
                  <td>{connection.engine}</td>
                  <td>{connection.host}</td>
                  <td>{connection.port}</td>
                  <td>{connection.database}</td>
                  <td>
                    <button type="button" onClick={() => void handleTest(connection.id)}>
                      Test
                    </button>
                    <button type="button" onClick={() => void handleDelete(connection.id)}>
                      Eliminar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="dashboard__section">
        <SourceAssign
          connections={connections}
          onCreated={() => void load()}
          onError={reportError}
        />
      </section>

      <section className="dashboard__section">
        <h2>Fuentes y asignaciones</h2>
        {sources.length === 0 ? (
          <p>No hay fuentes registradas.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Fuente</th>
                <th>Tipo</th>
                <th>Conexión actual</th>
                <th>Cambio de base en vivo</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((source) => (
                <tr key={source.name}>
                  <td>{source.name}</td>
                  <td>{source.parent_type}</td>
                  <td>{source.connection_id ?? "sin asignar"}</td>
                  <td>
                    <SwitchControl
                      source={source}
                      connections={connections}
                      onSwitched={handleSwitched}
                      onError={reportError}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

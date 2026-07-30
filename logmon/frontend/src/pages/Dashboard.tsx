import { useCallback, useEffect, useState } from "react";

import ConnectionForm from "../components/ConnectionForm";
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
  const [pendingSource, setPendingSource] = useState<string | null>(null);
  const [selection, setSelection] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [conns, srcs] = await Promise.all([connectionsApi.list(), sourcesApi.list()]);
      setConnections(conns);
      setSources(srcs);
      setSelection((prev) => {
        const next: Record<string, string> = { ...prev };
        for (const source of srcs) {
          if (!next[source.name]) {
            next[source.name] = source.connection_id ?? "";
          }
        }
        return next;
      });
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

  async function handleSwitch(sourceName: string) {
    const target = selection[sourceName];
    if (!target) {
      setFeedback({ kind: "error", message: "Elegí una conexión destino" });
      return;
    }

    setPendingSource(sourceName);
    setFeedback(null);

    try {
      const result = await sourcesApi.switch(sourceName, target);
      setSources((prev) =>
        prev.map((source) => (source.name === sourceName ? result.source : source)),
      );
      setFeedback({
        kind: "ok",
        message: `${sourceName} ahora escribe en ${target}`,
      });
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "El cambio de base fue abortado";
      setFeedback({ kind: "error", message });
      await load();
    } finally {
      setPendingSource(null);
    }
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
                <th>Cambiar a</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {sources.map((source) => (
                <tr key={source.name}>
                  <td>{source.name}</td>
                  <td>{source.parent_type}</td>
                  <td>{source.connection_id ?? "sin asignar"}</td>
                  <td>
                    <select
                      value={selection[source.name] ?? ""}
                      onChange={(event) =>
                        setSelection((prev) => ({
                          ...prev,
                          [source.name]: event.target.value,
                        }))
                      }
                    >
                      <option value="">Seleccionar...</option>
                      {connections.map((connection) => (
                        <option key={connection.id} value={connection.id}>
                          {connection.id} — {connection.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <button
                      type="button"
                      onClick={() => void handleSwitch(source.name)}
                      disabled={
                        pendingSource === source.name ||
                        !selection[source.name] ||
                        selection[source.name] === source.connection_id
                      }
                    >
                      {pendingSource === source.name ? "Cambiando..." : "Cambiar base"}
                    </button>
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

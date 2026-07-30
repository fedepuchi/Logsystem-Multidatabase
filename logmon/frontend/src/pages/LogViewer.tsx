import { useCallback, useEffect, useState } from "react";

import LogDetail from "../components/LogDetail";
import LogTable from "../components/LogTable";
import {
  ApiError,
  connectionsApi,
  logsApi,
  sourcesApi,
  type Connection,
  type Estado,
  type LogQuery,
  type LogSummary,
  type Source,
} from "../api/client";

const EMPTY_FILTERS: LogQuery = {
  source: "",
  estado: undefined,
  metodo: "",
  fecha_inicio: "",
  fecha_fin: "",
};

function toIsoOrUndefined(value: string | undefined): string | undefined {
  if (!value) {
    return undefined;
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

export default function LogViewer() {
  const [logs, setLogs] = useState<LogSummary[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [filters, setFilters] = useState<LogQuery>(EMPTY_FILTERS);
  const [selected, setSelected] = useState<LogSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([connectionsApi.list(), sourcesApi.list()])
      .then(([conns, srcs]) => {
        setConnections(conns);
        setSources(srcs);
      })
      .catch(() => {
        setConnections([]);
        setSources([]);
      });
  }, []);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const query: LogQuery = {
        source: filters.source || undefined,
        estado: filters.estado,
        metodo: filters.metodo || undefined,
        fecha_inicio: toIsoOrUndefined(filters.fecha_inicio),
        fecha_fin: toIsoOrUndefined(filters.fecha_fin),
      };

      const result = await logsApi.list(query);
      setLogs(result);
      setSelected(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "No se pudieron cargar los logs";
      setError(message);
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  async function handleDemo() {
    setError(null);
    try {
      await logsApi.demo();
      await loadLogs();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "No se pudieron generar los datos";
      setError(message);
    }
  }

  function update<K extends keyof LogQuery>(key: K, value: LogQuery[K]) {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <div className="log-viewer">
      <header className="log-viewer__header">
        <h1>Visualizar logs</h1>
        <div className="log-viewer__actions">
          <button type="button" onClick={() => void handleDemo()}>
            Generar datos demo
          </button>
          <button type="button" onClick={() => void loadLogs()} disabled={loading}>
            {loading ? "Cargando..." : "Refrescar"}
          </button>
        </div>
      </header>

      <section className="filters">
        <label>
          <span>Fuente</span>
          <select
            value={filters.source ?? ""}
            onChange={(event) => update("source", event.target.value)}
          >
            <option value="">Todas</option>
            {sources.map((source) => (
              <option key={source.name} value={source.name}>
                {source.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Estado</span>
          <select
            value={filters.estado ?? ""}
            onChange={(event) =>
              update("estado", event.target.value ? (event.target.value as Estado) : undefined)
            }
          >
            <option value="">Todos</option>
            <option value="OK">OK</option>
            <option value="ERROR">ERROR</option>
          </select>
        </label>

        <label>
          <span>Método</span>
          <input
            type="text"
            value={filters.metodo ?? ""}
            onChange={(event) => update("metodo", event.target.value)}
            placeholder="POST"
          />
        </label>

        <label>
          <span>Desde</span>
          <input
            type="datetime-local"
            value={filters.fecha_inicio ?? ""}
            onChange={(event) => update("fecha_inicio", event.target.value)}
          />
        </label>

        <label>
          <span>Hasta</span>
          <input
            type="datetime-local"
            value={filters.fecha_fin ?? ""}
            onChange={(event) => update("fecha_fin", event.target.value)}
          />
        </label>

        <button type="button" onClick={() => setFilters(EMPTY_FILTERS)}>
          Limpiar
        </button>
      </section>

      {error && <p className="feedback feedback--error">{error}</p>}

      <div className="log-viewer__body">
        <div className="log-viewer__table">
          <LogTable
            logs={logs}
            connections={connections}
            selectedId={selected?.id ?? null}
            onSelect={setSelected}
            loading={loading}
          />
        </div>

        <LogDetail summary={selected} connections={connections} />
      </div>
    </div>
  );
}

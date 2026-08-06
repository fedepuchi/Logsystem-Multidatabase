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

const PAGE_SIZE = 50;

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
  const [autoRefresh, setAutoRefresh] = useState(false);

  // offset de la página actual; el tamaño de página es fijo (PAGE_SIZE).
  const [offset, setOffset] = useState(0);
  // El backend no devuelve un total, así que "hay página siguiente" se infiere
  // de si la última carga trajo una página llena (logs.length === PAGE_SIZE).
  const [hasNextPage, setHasNextPage] = useState(false);

  useEffect(() => {
    Promise.all([connectionsApi.list(), sourcesApi.list()])
      .then(([conns, srcs]) => {
        setConnections(conns);
        setSources(srcs);
      })
      .catch(() => {
        setConnections([]);
        setSources([]);
        setError("No se pudieron cargar las conexiones o fuentes");
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
        limit: PAGE_SIZE,
        offset,
      };

      const result = await logsApi.list(query);
      setLogs(result);
      setHasNextPage(result.length === PAGE_SIZE);
      setSelected(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "No se pudieron cargar los logs";
      setError(message);
      setLogs([]);
      setHasNextPage(false);
    } finally {
      setLoading(false);
    }
  }, [filters, offset]);

  useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  useEffect(() => {
    if (!autoRefresh) {
      return;
    }

    const intervalId = setInterval(() => {
      void loadLogs();
    }, 5000);

    return () => clearInterval(intervalId);
  }, [autoRefresh, loadLogs]);

  async function handleDemo() {
    setError(null);
    try {
      await logsApi.demo();
      // reset offset: demo data replaces the dataset, current page may no
      // longer exist and would silently render empty otherwise.
      setOffset(0);
      await loadLogs();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "No se pudieron generar los datos";
      setError(message);
    }
  }

  function update<K extends keyof LogQuery>(key: K, value: LogQuery[K]) {
    setFilters((prev) => ({ ...prev, [key]: value }));
    // Cambiar cualquier filtro vuelve a la primera página: si no reseteamos
    // el offset, se puede quedar filtrando "página 3" sobre un resultado
    // nuevo mucho más chico y mostrar una página vacía sin explicación.
    setOffset(0);
  }

  function handleClearFilters() {
    setFilters(EMPTY_FILTERS);
    setOffset(0);
  }

  function handlePrevPage() {
    setOffset((prev) => Math.max(0, prev - PAGE_SIZE));
  }

  function handleNextPage() {
    if (hasNextPage) {
      setOffset((prev) => prev + PAGE_SIZE);
    }
  }

  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

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
          <label className="log-viewer__auto-refresh">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(event) => setAutoRefresh(event.target.checked)}
            />
            <span>Actualizar automáticamente</span>
          </label>
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

        <button type="button" onClick={handleClearFilters}>
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

          <div className="pagination">
            <button
              type="button"
              onClick={handlePrevPage}
              disabled={loading || offset === 0}
            >
              ← Anterior
            </button>
            <span className="pagination__page">Página {currentPage}</span>
            <button
              type="button"
              onClick={handleNextPage}
              disabled={loading || !hasNextPage}
            >
              Siguiente →
            </button>
          </div>
        </div>

        <LogDetail summary={selected} connections={connections} />
      </div>
    </div>
  );
}
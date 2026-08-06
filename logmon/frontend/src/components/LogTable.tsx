import DbOriginBadge from "./DbOriginBadge";
import EstadoTabla from "./EstadoTabla";
import type { Connection, Engine, LogSummary } from "../api/client";

interface LogTableProps {
  logs: LogSummary[];
  connections: Connection[];
  selectedId: string | null;
  onSelect: (log: LogSummary) => void;
  loading?: boolean;
  error?: string | null;
}

function formatFecha(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function LogTable({
  logs,
  connections,
  selectedId,
  onSelect,
  loading,
  error,
}: LogTableProps) {
  const engineById = new Map<string, Engine>(
    connections.map((connection) => [connection.id, connection.engine]),
  );

  const sinFilas = logs.length === 0;

  if (loading || error || sinFilas) {
    return <EstadoTabla loading={loading} error={error} vacio={sinFilas} />;
  }

  return (
    <table className="table table--logs">
      <thead>
        <tr>
          <th>Fecha</th>
          <th>Fuente</th>
          <th>Tipo</th>
          <th>Método</th>
          <th>Entrada</th>
          <th>Resultado</th>
          <th>Tiempo</th>
          <th>Estado</th>
          <th>Origen</th>
        </tr>
      </thead>
      <tbody>
        {logs.map((log) => (
          <tr
            key={log.id}
            onClick={() => onSelect(log)}
            className={log.id === selectedId ? "row row--selected" : "row"}
          >
            <td>{formatFecha(log.fecha)}</td>
            <td>{log.source_id}</td>
            <td>{log.parent_type}</td>
            <td>{log.metodo}</td>
            <td>{log.entrada}</td>
            <td>{log.resultado}</td>
            <td>{log.tiempo_ms} ms</td>
            <td>
              <span
                className={log.estado === "ERROR" ? "badge badge--error" : "badge badge--ok"}
              >
                {log.estado}
              </span>
            </td>
            <td>
              <DbOriginBadge
                connectionId={log.connection_id}
                engine={log.connection_id ? engineById.get(log.connection_id) : null}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

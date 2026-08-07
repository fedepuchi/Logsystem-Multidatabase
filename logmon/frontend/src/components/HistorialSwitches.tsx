import { useEffect, useState } from "react";

import { ApiError, sourcesApi, type SourceHistory } from "../api/client";

interface HistorialSwitchesProps {
  /** Nombre de la fuente. Si es null, el panel no consulta nada. */
  source: string | null;
}

function formatFecha(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

/**
 * Historial de cambios de motor de una fuente.
 *
 * Es la evidencia visual de que un switch no perdió nada: `connections` son
 * todas las bases por las que pasó la fuente, y el visor hace fan-out sobre esa
 * misma lista. Que aparezcan varias es lo que explica por qué siguen viéndose
 * los logs viejos después de cambiar de motor.
 *
 * La auditoría se guardaba desde la v1 y no se mostraba en ningún lado.
 */
export default function HistorialSwitches({ source }: HistorialSwitchesProps) {
  const [historia, setHistoria] = useState<SourceHistory | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!source) {
      setHistoria(null);
      return;
    }

    let vigente = true;
    setLoading(true);
    setError(null);

    sourcesApi
      .history(source)
      .then((datos) => {
        // Sin esta guarda, cambiar de fuente rápido puede pintar la respuesta
        // de la anterior si llega más tarde.
        if (vigente) setHistoria(datos);
      })
      .catch((err) => {
        if (!vigente) return;
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el historial");
        setHistoria(null);
      })
      .finally(() => {
        if (vigente) setLoading(false);
      });

    return () => {
      vigente = false;
    };
  }, [source]);

  if (!source) {
    return <p className="empty">Elegí una fuente para ver su historial.</p>;
  }

  if (loading) {
    return <p className="empty">Cargando historial…</p>;
  }

  if (error) {
    return (
      <p className="feedback feedback--error" role="status">
        {error}
      </p>
    );
  }

  if (!historia || historia.audit.length === 0) {
    return <p className="empty">La fuente «{source}» todavía no cambió de motor.</p>;
  }

  return (
    <div className="historial">
      <p className="historial__resumen">
        Escribió en <strong>{historia.connections.length}</strong>{" "}
        {historia.connections.length === 1 ? "conexión" : "conexiones"}:{" "}
        {historia.connections.join(", ")}
      </p>

      <table className="table">
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Desde</th>
            <th>Hacia</th>
            <th>Resultado</th>
            <th>Detalle</th>
          </tr>
        </thead>
        <tbody>
          {historia.audit.map((cambio) => (
            <tr key={cambio.id}>
              <td>{formatFecha(cambio.created_at)}</td>
              <td>{cambio.from_connection_id ?? "—"}</td>
              <td>{cambio.to_connection_id}</td>
              <td>
                <span
                  className={`badge badge--${cambio.status === "OK" ? "ok" : "error"}`}
                >
                  {cambio.status === "OK" ? "aplicado" : "abortado"}
                </span>
              </td>
              <td className="historial__detalle">{cambio.detail ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

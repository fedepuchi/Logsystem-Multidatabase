import { useCallback, useEffect, useState } from "react";

import { ApiError, statsApi, type LogStats } from "../api/client";

interface PanelMetricasProps {
  /** Si se indica, los números se limitan a esa fuente. */
  source?: string;
}

function porcentaje(valor: number): string {
  return `${(valor * 100).toFixed(1)} %`;
}

/**
 * Totales, tasa de error y reparto por motor.
 *
 * Todo viene calculado de `GET /api/stats`: hacerlo en el cliente sobre los logs
 * de la página visible daría los números de esa página y no los reales.
 */
export default function PanelMetricas({ source }: PanelMetricasProps) {
  const [stats, setStats] = useState<LogStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      setStats(await statsApi.get(source));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudieron cargar las métricas");
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, [source]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  if (loading) {
    return <p className="empty">Cargando métricas…</p>;
  }

  if (error) {
    return (
      <p className="feedback feedback--error" role="status">
        {error}
      </p>
    );
  }

  if (!stats || stats.total_logs === 0) {
    return <p className="empty">Todavía no hay logs para medir.</p>;
  }

  return (
    <div className="metricas">
      {stats.unavailable.length > 0 && (
        // Sin este aviso los totales se leerían como completos cuando no lo son.
        <p className="feedback feedback--warn" role="status">
          {stats.unavailable.length === 1 ? "Un motor no respondió" : "Varios motores no respondieron"}
          {` (${stats.unavailable.join(", ")}): los números de abajo los excluyen.`}
        </p>
      )}

      <div className="metricas__tarjetas">
        <div className="metrica">
          <span className="metrica__numero">{stats.total_logs}</span>
          <span className="metrica__titulo">Logs totales</span>
        </div>
        <div className="metrica metrica--error">
          <span className="metrica__numero">{stats.error_count}</span>
          <span className="metrica__titulo">En error</span>
        </div>
        <div className="metrica">
          <span className="metrica__numero">{porcentaje(stats.error_rate)}</span>
          <span className="metrica__titulo">Tasa de error</span>
        </div>
        <div className="metrica">
          <span className="metrica__numero">{stats.engines.length}</span>
          <span className="metrica__titulo">
            {stats.engines.length === 1 ? "Motor con datos" : "Motores con datos"}
          </span>
        </div>
      </div>

      <table className="table">
        <thead>
          <tr>
            <th>Motor</th>
            <th>Conexiones</th>
            <th>Logs</th>
            <th>Errores</th>
            <th>Tasa</th>
          </tr>
        </thead>
        <tbody>
          {stats.engines.map((motor) => (
            <tr key={motor.engine}>
              <td>{motor.engine}</td>
              <td>{motor.connection_ids.join(", ")}</td>
              <td>{motor.total_logs}</td>
              <td>{motor.error_count}</td>
              <td>{porcentaje(motor.error_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <button type="button" onClick={() => void cargar()}>
        Actualizar
      </button>
    </div>
  );
}

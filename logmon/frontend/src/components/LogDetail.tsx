import { useEffect, useState } from "react";

import DbOriginBadge from "./DbOriginBadge";
import StepBadge from "./StepBadge";
import { ApiError, logsApi, type Connection, type Engine, type LogRecord, type LogSummary } from "../api/client";

interface LogDetailProps {
  summary: LogSummary | null;
  connections: Connection[];
}

export default function LogDetail({ summary, connections }: LogDetailProps) {
  const [record, setRecord] = useState<LogRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!summary) {
      setRecord(null);
      setError(null);
      return;
    }

    if (!summary.connection_id) {
      setRecord(null);
      setError("El log no trae connection_id, no se puede consultar el detalle.");
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    logsApi
      .get(summary.id, summary.connection_id)
      .then((data) => {
        if (!cancelled) {
          setRecord(data);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setRecord(null);
          setError(err instanceof ApiError ? err.message : "No se pudo cargar el detalle");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [summary]);

  if (!summary) {
    return (
      <aside className="log-detail log-detail--empty">
        <p>Seleccioná un log de la tabla para ver sus pasos.</p>
      </aside>
    );
  }

  const engine: Engine | null = summary.connection_id
    ? connections.find((c) => c.id === summary.connection_id)?.engine ?? null
    : null;

  return (
    <aside className="log-detail">
      <header className="log-detail__header">
        <h3>{summary.entrada}</h3>
        <DbOriginBadge connectionId={summary.connection_id} engine={engine} />
      </header>

      <dl className="log-detail__meta">
        <dt>ID</dt>
        <dd>{summary.id}</dd>
        <dt>Fuente</dt>
        <dd>
          {summary.source_id} ({summary.parent_type})
        </dd>
        <dt>Método</dt>
        <dd>{summary.metodo}</dd>
        <dt>Resultado</dt>
        <dd>{summary.resultado}</dd>
        <dt>Tiempo total</dt>
        <dd>{summary.tiempo_ms} ms</dd>
        <dt>Estado</dt>
        <dd>
          <span className={summary.estado === "ERROR" ? "badge badge--error" : "badge badge--ok"}>
            {summary.estado}
          </span>
        </dd>
      </dl>

      <h4>Pasos</h4>

      {loading && <p>Cargando pasos...</p>}
      {error && <p className="feedback feedback--error">{error}</p>}

      {!loading && !error && record && record.steps.length === 0 && <p>El log no tiene pasos.</p>}

      {!loading && !error && record && record.steps.length > 0 && (
        <ol className="steps">
          {record.steps.map((step) => (
            <li key={step.orden} className="steps__item">
              <StepBadge tipo={step.tipo} />
              <span className="steps__content">{step.contenido}</span>
              <span className="steps__duration">
                {step.duration_ms === null ? "—" : `${step.duration_ms} ms`}
              </span>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}

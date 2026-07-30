import type { Engine } from "../api/client";

const LABEL_BY_ENGINE: Record<Engine, string> = {
  mariadb: "MariaDB",
  postgres: "PostgreSQL",
  sqlserver: "SQL Server",
  mongo: "MongoDB",
  redis: "Redis",
};

interface DbOriginBadgeProps {
  connectionId?: string | null;
  engine?: Engine | null;
}

export default function DbOriginBadge({ connectionId, engine }: DbOriginBadgeProps) {
  if (!connectionId) {
    return <span className="badge badge--muted">sin origen</span>;
  }

  const label = engine ? LABEL_BY_ENGINE[engine] : null;

  return (
    <span className={`badge badge--db badge--db-${engine ?? "unknown"}`}>
      {label ? `${connectionId} · ${label}` : connectionId}
    </span>
  );
}

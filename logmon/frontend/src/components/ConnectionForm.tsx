import { useState, type FormEvent } from "react";

import {
  ApiError,
  connectionsApi,
  type Connection,
  type ConnectionIn,
  type Engine,
} from "../api/client";

const ENGINES: { value: Engine; label: string; defaultPort: number }[] = [
  { value: "mariadb", label: "MariaDB", defaultPort: 3306 },
  { value: "postgres", label: "PostgreSQL", defaultPort: 5432 },
  { value: "sqlserver", label: "SQL Server", defaultPort: 1433 },
  { value: "mongo", label: "MongoDB", defaultPort: 27017 },
  { value: "redis", label: "Redis", defaultPort: 6379 },
];

const EMPTY_FORM: ConnectionIn = {
  name: "",
  engine: "postgres",
  host: "localhost",
  port: 5432,
  user: "",
  password: "",
  database: "",
};

type Feedback = { kind: "ok" | "error"; message: string };

interface ConnectionFormProps {
  onCreated?: (connection: Connection) => void;
}

export default function ConnectionForm({ onCreated }: ConnectionFormProps) {
  const [form, setForm] = useState<ConnectionIn>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [created, setCreated] = useState<Connection | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  function update<K extends keyof ConnectionIn>(key: K, value: ConnectionIn[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setFeedback(null);
  }

  function handleEngineChange(engine: Engine) {
    const preset = ENGINES.find((item) => item.value === engine);
    setForm((prev) => ({
      ...prev,
      engine,
      port: preset ? preset.defaultPort : prev.port,
    }));
    setFeedback(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFeedback(null);

    try {
      const connection = await connectionsApi.create(form);
      setCreated(connection);
      setForm(EMPTY_FORM);
      setFeedback({ kind: "ok", message: `Conexión ${connection.id} creada` });
      onCreated?.(connection);
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "No se pudo crear la conexión";
      setFeedback({ kind: "error", message });
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    if (!created) {
      return;
    }

    setTesting(true);
    setFeedback(null);

    try {
      const result = await connectionsApi.test(created.id);
      setFeedback({
        kind: result.success ? "ok" : "error",
        message: result.message,
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "El test de conexión falló";
      setFeedback({ kind: "error", message });
    } finally {
      setTesting(false);
    }
  }

  const disabled = saving || testing;

  return (
    <form className="connection-form" onSubmit={handleSubmit}>
      <h2>Add conexión</h2>

      <label>
        <span>Nombre</span>
        <input
          type="text"
          value={form.name}
          onChange={(event) => update("name", event.target.value)}
          placeholder="C1 MariaDB"
          required
          disabled={disabled}
        />
      </label>

      <label>
        <span>Motor</span>
        <select
          value={form.engine}
          onChange={(event) => handleEngineChange(event.target.value as Engine)}
          disabled={disabled}
        >
          {ENGINES.map((engine) => (
            <option key={engine.value} value={engine.value}>
              {engine.label}
            </option>
          ))}
        </select>
      </label>

      <label>
        <span>Host</span>
        <input
          type="text"
          value={form.host}
          onChange={(event) => update("host", event.target.value)}
          required
          disabled={disabled}
        />
      </label>

      <label>
        <span>Puerto</span>
        <input
          type="number"
          min={1}
          max={65535}
          value={form.port}
          onChange={(event) => update("port", Number(event.target.value))}
          required
          disabled={disabled}
        />
      </label>

      <label>
        <span>Usuario</span>
        <input
          type="text"
          value={form.user}
          onChange={(event) => update("user", event.target.value)}
          required
          disabled={disabled}
        />
      </label>

      <label>
        <span>Contraseña</span>
        <input
          type="password"
          value={form.password}
          onChange={(event) => update("password", event.target.value)}
          required
          disabled={disabled}
        />
      </label>

      <label>
        <span>Base de datos</span>
        <input
          type="text"
          value={form.database}
          onChange={(event) => update("database", event.target.value)}
          required
          disabled={disabled}
        />
      </label>

      <div className="connection-form__actions">
        <button type="submit" disabled={disabled}>
          {saving ? "Guardando..." : "Guardar conexión"}
        </button>

        <button type="button" onClick={handleTest} disabled={disabled || !created}>
          {testing ? "Probando..." : "Test"}
        </button>
      </div>

      {feedback && (
        <p className={`feedback feedback--${feedback.kind}`} role="status">
          {feedback.message}
        </p>
      )}
    </form>
  );
}

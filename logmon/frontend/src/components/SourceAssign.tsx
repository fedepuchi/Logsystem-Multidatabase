import { useState, type FormEvent } from "react";

import {
  ApiError,
  sourcesApi,
  type Connection,
  type ParentType,
  type SourceIn,
} from "../api/client";

const PARENT_TYPES: ParentType[] = ["API", "WEB", "SISTEMA"];

const EMPTY_FORM: SourceIn = {
  name: "",
  parent_type: "API",
};

interface SourceAssignProps {
  connections: Connection[];
  onCreated: () => void;
  onError: (message: string) => void;
}

export default function SourceAssign({ connections, onCreated, onError }: SourceAssignProps) {
  const [form, setForm] = useState<SourceIn>(EMPTY_FORM);
  const [connectionId, setConnectionId] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);

    try {
      await sourcesApi.create(form);

      if (connectionId) {
        await sourcesApi.switch(form.name, connectionId);
      }

      setForm(EMPTY_FORM);
      setConnectionId("");
      onCreated();
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "No se pudo crear la fuente";
      onError(message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="source-assign" onSubmit={handleSubmit}>
      <h3>Nueva fuente</h3>

      <label>
        <span>Nombre</span>
        <input
          type="text"
          value={form.name}
          onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
          placeholder="APP1"
          required
          disabled={saving}
        />
      </label>

      <label>
        <span>Tipo</span>
        <select
          value={form.parent_type}
          onChange={(event) =>
            setForm((prev) => ({ ...prev, parent_type: event.target.value as ParentType }))
          }
          disabled={saving}
        >
          {PARENT_TYPES.map((tipo) => (
            <option key={tipo} value={tipo}>
              {tipo}
            </option>
          ))}
        </select>
      </label>

      <label>
        <span>Conexión inicial</span>
        <select
          value={connectionId}
          onChange={(event) => setConnectionId(event.target.value)}
          disabled={saving}
        >
          <option value="">Sin asignar</option>
          {connections.map((connection) => (
            <option key={connection.id} value={connection.id}>
              {connection.id} — {connection.name}
            </option>
          ))}
        </select>
      </label>

      <button type="submit" disabled={saving}>
        {saving ? "Guardando..." : "Crear fuente"}
      </button>
    </form>
  );
}

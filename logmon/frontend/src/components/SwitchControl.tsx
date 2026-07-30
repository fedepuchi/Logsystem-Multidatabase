import { useState } from "react";

import { ApiError, sourcesApi, type Connection, type Source } from "../api/client";

interface SwitchControlProps {
  source: Source;
  connections: Connection[];
  onSwitched: (source: Source) => void;
  onError: (message: string) => void;
}

export default function SwitchControl({
  source,
  connections,
  onSwitched,
  onError,
}: SwitchControlProps) {
  const [target, setTarget] = useState(source.connection_id ?? "");
  const [pending, setPending] = useState(false);

  const unchanged = target === "" || target === source.connection_id;

  async function handleSwitch() {
    if (unchanged) {
      return;
    }

    setPending(true);
    try {
      const result = await sourcesApi.switch(source.name, target);
      onSwitched(result.source);
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "El cambio de base fue abortado";
      onError(`${source.name}: ${message}`);
      setTarget(source.connection_id ?? "");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="switch-control">
      <select
        value={target}
        onChange={(event) => setTarget(event.target.value)}
        disabled={pending}
      >
        <option value="">Seleccionar...</option>
        {connections.map((connection) => (
          <option key={connection.id} value={connection.id}>
            {connection.id} — {connection.name}
          </option>
        ))}
      </select>

      <button type="button" onClick={() => void handleSwitch()} disabled={pending || unchanged}>
        {pending ? "Cambiando..." : "Cambiar base"}
      </button>
    </div>
  );
}

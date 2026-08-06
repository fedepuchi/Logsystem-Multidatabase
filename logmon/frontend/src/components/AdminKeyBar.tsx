import { useState, type FormEvent } from "react";

import { adminKeyStore } from "../api/client";

interface AdminKeyBarProps {
  /** Se llama al guardar o borrar para que el panel vuelva a pedir los datos. */
  onChanged: () => void;
}

/**
 * Clave de administración del panel (header X-Admin-Key).
 *
 * Sólo abre la administración: conexiones, fuentes, switch y visor. Las
 * aplicaciones que ingestan no usan esta clave sino la API key de su fuente.
 * Si el backend corre sin ADMIN_API_KEY —el modo de la demo— se puede dejar
 * vacía y todo funciona igual.
 */
export default function AdminKeyBar({ onChanged }: AdminKeyBarProps) {
  const [value, setValue] = useState(adminKeyStore.get());
  const [editing, setEditing] = useState(adminKeyStore.get() === "");

  const saved = adminKeyStore.get();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    adminKeyStore.set(value);
    setEditing(false);
    onChanged();
  }

  function handleClear() {
    adminKeyStore.clear();
    setValue("");
    setEditing(true);
    onChanged();
  }

  if (!editing) {
    return (
      <div className="admin-key">
        <span className="admin-key__status" title="Header X-Admin-Key">
          Clave de admin activa
        </span>
        <button type="button" onClick={() => setEditing(true)}>
          Cambiar
        </button>
        <button type="button" onClick={handleClear}>
          Quitar
        </button>
      </div>
    );
  }

  return (
    <form className="admin-key" onSubmit={handleSubmit}>
      <input
        type="password"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Clave de admin"
        autoComplete="off"
        aria-label="Clave de administración"
      />
      <button type="submit">Guardar</button>
      {saved && (
        <button type="button" onClick={() => { setValue(saved); setEditing(false); }}>
          Cancelar
        </button>
      )}
    </form>
  );
}

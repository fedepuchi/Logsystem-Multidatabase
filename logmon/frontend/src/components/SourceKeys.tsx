import { useCallback, useEffect, useState, type FormEvent } from "react";

import { ApiError, sourcesApi, type ApiKey, type Source } from "../api/client";

interface SourceKeysProps {
  sources: Source[];
  onError: (message: string) => void;
}

function formatFecha(valor: string | null): string {
  if (!valor) {
    return "nunca";
  }
  const fecha = new Date(valor);
  return Number.isNaN(fecha.getTime()) ? valor : fecha.toLocaleString();
}

/**
 * Emisión y revocación de las API keys de ingesta de una fuente.
 *
 * El secreto se muestra una única vez, al crearlo: el backend guarda sólo su
 * hash, así que no hay forma de volver a verlo. Si se pierde, se revoca esa
 * key y se emite otra.
 */
export default function SourceKeys({ sources, onError }: SourceKeysProps) {
  const [selected, setSelected] = useState("");
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [nombre, setNombre] = useState("");
  const [loading, setLoading] = useState(false);
  const [creando, setCreando] = useState(false);
  const [revelada, setRevelada] = useState<{ preview: string; secret: string } | null>(null);

  // La fuente elegida se mantiene mientras exista; si se borra, se cae a la primera.
  useEffect(() => {
    if (sources.length === 0) {
      setSelected("");
      return;
    }
    if (!sources.some((source) => source.name === selected)) {
      setSelected(sources[0].name);
    }
  }, [sources, selected]);

  const load = useCallback(async () => {
    if (!selected) {
      setKeys([]);
      return;
    }

    setLoading(true);
    try {
      setKeys(await sourcesApi.keys(selected));
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "No se pudieron cargar las API keys";
      onError(message);
      setKeys([]);
    } finally {
      setLoading(false);
    }
  }, [selected, onError]);

  useEffect(() => {
    // Al cambiar de fuente el secreto revelado deja de corresponder: se oculta.
    setRevelada(null);
    void load();
  }, [load]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) {
      return;
    }

    setCreando(true);
    try {
      const creada = await sourcesApi.createKey(selected, nombre);
      setRevelada({ preview: creada.preview, secret: creada.api_key });
      setNombre("");
      await load();
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "No se pudo emitir la API key";
      onError(message);
    } finally {
      setCreando(false);
    }
  }

  async function handleRevoke(key: ApiKey) {
    try {
      await sourcesApi.revokeKey(key.source_id, key.id);
      if (revelada?.preview === key.preview) {
        setRevelada(null);
      }
      await load();
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "No se pudo revocar la API key";
      onError(message);
    }
  }

  return (
    <div className="source-keys">
      <h2>API keys de ingesta</h2>
      <p className="source-keys__hint">
        Cada fuente escribe sus logs con sus propias keys, en el header{" "}
        <code>X-API-Key</code>. No sirven para administrar, y la clave de
        administración no sirve para ingestar.
      </p>

      {sources.length === 0 ? (
        <p>No hay fuentes registradas.</p>
      ) : (
        <>
          <form className="source-keys__form" onSubmit={handleCreate}>
            <label>
              <span>Fuente</span>
              <select value={selected} onChange={(event) => setSelected(event.target.value)}>
                {sources.map((source) => (
                  <option key={source.name} value={source.name}>
                    {source.name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span>Nombre de la key</span>
              <input
                type="text"
                value={nombre}
                onChange={(event) => setNombre(event.target.value)}
                placeholder="produccion"
                disabled={creando}
              />
            </label>

            <button type="submit" disabled={creando || !selected}>
              {creando ? "Emitiendo..." : "Emitir key"}
            </button>
          </form>

          {revelada && (
            <p className="source-keys__reveal" role="status">
              <strong>Copiala ahora:</strong> es la única vez que se muestra.
              <code>{revelada.secret}</code>
            </p>
          )}

          {loading ? (
            <p>Cargando...</p>
          ) : keys.length === 0 ? (
            <p>{selected} todavía no tiene keys emitidas.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Key</th>
                  <th>Creada</th>
                  <th>Último uso</th>
                  <th>Estado</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {keys.map((key) => (
                  <tr key={key.id}>
                    <td>{key.name || "—"}</td>
                    <td>
                      <code>{key.preview}…</code>
                    </td>
                    <td>{formatFecha(key.created_at)}</td>
                    <td>{formatFecha(key.last_used_at)}</td>
                    <td>{key.revoked_at ? `revocada ${formatFecha(key.revoked_at)}` : "activa"}</td>
                    <td>
                      {!key.revoked_at && (
                        <button type="button" onClick={() => void handleRevoke(key)}>
                          Revocar
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}

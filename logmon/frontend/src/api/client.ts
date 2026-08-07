export type ParentType = "API" | "WEB" | "SISTEMA";
export type StepType = "ENTRADA" | "SALIDA" | "ERROR";
export type Estado = "OK" | "ERROR";
export type Engine = "mariadb" | "postgres" | "sqlserver" | "mongo" | "redis";

export interface LogStep {
  orden: number;
  tipo: StepType;
  contenido: string;
  duration_ms: number | null;
}

export interface LogRecord {
  id: string;
  source_id: string;
  parent_type: ParentType;
  entrada: string;
  resultado: string;
  metodo: string;
  tiempo_ms: number;
  estado: Estado;
  fecha: string;
  steps: LogStep[];
  connection_id?: string | null;
}

export interface LogSummary {
  id: string;
  source_id: string;
  parent_type: ParentType;
  entrada: string;
  resultado: string;
  metodo: string;
  tiempo_ms: number;
  estado: Estado;
  fecha: string;
  connection_id?: string | null;
}

export interface ConnectionIn {
  name: string;
  engine: Engine;
  host: string;
  port: number;
  user: string;
  password: string;
  database: string;
}

export interface Connection {
  id: string;
  name: string;
  engine: Engine;
  host: string;
  port: number;
  user: string;
  database: string;
}

export interface SourceIn {
  name: string;
  parent_type: ParentType;
}

export interface Source {
  name: string;
  parent_type: ParentType;
  connection_id: string | null;
}

export interface LogStepInput {
  orden: number;
  tipo: StepType;
  contenido: string;
  duration_ms?: number | null;
}

/** Payload de ingesta: el id (ULID) y los derivados los pone el servidor. */
export interface LogCreateInput {
  source_id: string;
  parent_type: ParentType;
  entrada: string;
  resultado: string;
  metodo: string;
  fecha?: string;
  steps: LogStepInput[];
}

export interface LogCreated {
  message: string;
  id: string;
  connection_id: string;
  estado: Estado;
  tiempo_ms: number;
}

/** Agregados de `GET /api/stats`, calculados en el backend. */
export interface LogStats {
  generated_at: string;
  bucket_minutes: number;
  total_logs: number;
  error_count: number;
  error_rate: number;
  engines: {
    engine: string;
    connection_ids: string[];
    total_logs: number;
    error_count: number;
    error_rate: number;
    volume: { start: string; total: number; errors: number }[];
  }[];
  /** Motores que no respondieron: el resto de los números los excluye. */
  unavailable: string[];
}

export interface SourceHistory {
  source: string;
  connections: string[];
  audit: {
    id: number;
    source_id: string;
    from_connection_id: string | null;
    to_connection_id: string;
    status: "OK" | "ABORTED";
    detail: string | null;
    created_at: string;
  }[];
}

export interface LogQuery {
  source?: string;
  estado?: Estado;
  metodo?: string;
  fecha_inicio?: string;
  fecha_fin?: string;
  limit?: number;
  offset?: number;
}

export interface TestResult {
  success: boolean;
  message: string;
}

/** API key de ingesta de una fuente. El secreto no está: sólo su preview. */
export interface ApiKey {
  id: string;
  source_id: string;
  name: string;
  preview: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

/** Alta de una key: la única respuesta que trae el secreto en texto plano. */
export interface ApiKeyCreated extends ApiKey {
  api_key: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

const ENV = (import.meta as unknown as { env?: Record<string, string | undefined> }).env;
const BASE_URL = (ENV?.VITE_API_URL ?? "").replace(/\/$/, "");

const ADMIN_KEY_STORAGE = "logmon.adminKey";
const ADMIN_HEADER = "X-Admin-Key";
const INGEST_HEADER = "X-API-Key";

function readStoredAdminKey(): string {
  try {
    return localStorage.getItem(ADMIN_KEY_STORAGE) ?? "";
  } catch {
    // Modo privado o entorno sin storage: la clave vive sólo en memoria.
    return "";
  }
}

let adminKey = readStoredAdminKey();

/**
 * Clave de administración del panel.
 *
 * Sólo abre la superficie de administración: la ingesta usa las API keys por
 * fuente, que el panel emite pero no guarda (el backend guarda su hash y el
 * secreto se muestra una única vez).
 *
 * Se persiste en localStorage para no tener que reescribirla en cada recarga.
 * Es una credencial de operador en una máquina de operador; si el backend
 * corre sin ADMIN_API_KEY, dejarla vacía es lo correcto.
 */
export const adminKeyStore = {
  get: () => adminKey,

  set(value: string) {
    adminKey = value.trim();
    try {
      if (adminKey) {
        localStorage.setItem(ADMIN_KEY_STORAGE, adminKey);
      } else {
        localStorage.removeItem(ADMIN_KEY_STORAGE);
      }
    } catch {
      // Sin storage la clave igual queda activa en esta pestaña.
    }
  },

  clear() {
    this.set("");
  },
};

function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

/**
 * Con qué credencial se firma la request.
 *
 * Los dos headers nunca viajan juntos: el backend separa administración de
 * ingesta y responde 403 si se usa la credencial de la otra superficie.
 */
type Auth = { sourceKey?: string };

async function request<T>(path: string, init?: RequestInit, auth: Auth = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string> | undefined) ?? {}),
  };

  if (auth.sourceKey) {
    headers[INGEST_HEADER] = auth.sourceKey;
  } else if (adminKey) {
    headers[ADMIN_HEADER] = adminKey;
  }

  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers });

  if (!response.ok) {
    let detail: unknown = null;
    let message = `${response.status} ${response.statusText}`;
    try {
      detail = await response.json();
      const parsed = detail as { detail?: unknown };
      if (typeof parsed?.detail === "string") {
        message = parsed.detail;
      }
    } catch {
      detail = await response.text().catch(() => null);
    }
    throw new ApiError(response.status, detail, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const connectionsApi = {
  list: () => request<Connection[]>("/api/connections"),

  get: (id: string) => request<Connection>(`/api/connections/${encodeURIComponent(id)}`),

  create: (data: ConnectionIn) =>
    request<Connection>("/api/connections", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (id: string, data: ConnectionIn) =>
    request<Connection>(`/api/connections/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  remove: (id: string) =>
    request<void>(`/api/connections/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  test: (id: string) =>
    request<TestResult>(`/api/connections/${encodeURIComponent(id)}/test`, {
      method: "POST",
    }),
};

export const statsApi = {
  /**
   * Los agregados salen del backend y no de la página que se está viendo: si se
   * calcularan en el cliente sobre los logs cargados, darían el total de esa
   * página y no el real.
   */
  get: (source?: string) =>
    request<LogStats>(
      `/api/stats${source ? `?source=${encodeURIComponent(source)}` : ""}`,
    ),
};

export const sourcesApi = {
  list: () => request<Source[]>("/api/sources"),

  get: (name: string) => request<Source>(`/api/sources/${encodeURIComponent(name)}`),

  create: (data: SourceIn) =>
    request<Source>("/api/sources", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  remove: (name: string, force = false) =>
    request<void>(
      `/api/sources/${encodeURIComponent(name)}${force ? "?force=true" : ""}`,
      { method: "DELETE" },
    ),

  history: (name: string) =>
    request<SourceHistory>(`/api/sources/${encodeURIComponent(name)}/history`),

  switch: (name: string, connectionId: string) =>
    request<{ message: string; source: Source }>(
      `/api/sources/${encodeURIComponent(name)}/switch`,
      {
        method: "POST",
        body: JSON.stringify({ connection_id: connectionId }),
      },
    ),

  /** Keys de ingesta de la fuente, vigentes y revocadas. */
  keys: (name: string) =>
    request<ApiKey[]>(`/api/sources/${encodeURIComponent(name)}/keys`),

  /** Emite una key nueva. El `api_key` de la respuesta no se puede recuperar después. */
  createKey: (name: string, keyName: string) =>
    request<ApiKeyCreated>(`/api/sources/${encodeURIComponent(name)}/keys`, {
      method: "POST",
      body: JSON.stringify({ name: keyName }),
    }),

  revokeKey: (name: string, keyId: string) =>
    request<void>(
      `/api/sources/${encodeURIComponent(name)}/keys/${encodeURIComponent(keyId)}`,
      { method: "DELETE" },
    ),
};

export const logsApi = {
  list: (query: LogQuery = {}) =>
    request<LogSummary[]>(`/api/logs${buildQuery({ ...query })}`),

  get: (id: string, connectionId: string) =>
    request<LogRecord>(
      `/api/logs/${encodeURIComponent(id)}${buildQuery({ conn: connectionId })}`,
    ),

  /**
   * Ingesta. Es la superficie de las aplicaciones monitoreadas, no la del
   * panel: si el backend tiene la auth encendida hay que pasar la API key de
   * la fuente, porque la clave de administración no habilita escribir logs.
   */
  create: (input: LogCreateInput, sourceKey?: string) =>
    request<LogCreated>(
      "/api/logs",
      {
        method: "POST",
        body: JSON.stringify(input),
      },
      { sourceKey },
    ),

  demo: () =>
    request<{ message: string; result: Record<string, unknown> }>("/api/logs/demo", {
      method: "POST",
    }),
};

export const healthApi = {
  check: () => request<{ status: string }>("/health"),
};

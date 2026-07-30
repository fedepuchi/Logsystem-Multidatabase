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

export interface LogQuery {
  source?: string;
  estado?: Estado;
  metodo?: string;
  fecha_inicio?: string;
  fecha_fin?: string;
}

export interface TestResult {
  success: boolean;
  message: string;
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

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
    request<{ message: string }>(`/api/connections/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  test: (id: string) =>
    request<TestResult>(`/api/connections/${encodeURIComponent(id)}/test`, {
      method: "POST",
    }),
};

export const sourcesApi = {
  list: () => request<Source[]>("/api/sources"),

  get: (name: string) => request<Source>(`/api/sources/${encodeURIComponent(name)}`),

  create: (data: SourceIn) =>
    request<Source>("/api/sources", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  remove: (name: string) =>
    request<{ message: string }>(`/api/sources/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),

  switch: (name: string, connectionId: string) =>
    request<{ message: string; source: Source }>(
      `/api/sources/${encodeURIComponent(name)}/switch`,
      {
        method: "POST",
        body: JSON.stringify({ connection_id: connectionId }),
      },
    ),
};

export const logsApi = {
  list: (query: LogQuery = {}) =>
    request<LogSummary[]>(`/api/logs${buildQuery({ ...query })}`),

  get: (id: string, connectionId: string) =>
    request<LogRecord>(
      `/api/logs/${encodeURIComponent(id)}${buildQuery({ conn: connectionId })}`,
    ),

  create: (record: LogRecord) =>
    request<{ message: string }>("/api/logs", {
      method: "POST",
      body: JSON.stringify(record),
    }),

  demo: () =>
    request<{ message: string }>("/api/logs/demo", {
      method: "POST",
    }),
};

export const healthApi = {
  check: () => request<{ status: string }>("/health"),
};

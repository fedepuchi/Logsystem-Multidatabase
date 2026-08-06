import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    logsApi: {
      ...actual.logsApi,
      get: vi.fn(),
    },
  };
});

import LogDetail from "./LogDetail";
import { logsApi, type Connection, type LogRecord, type LogSummary } from "../api/client";

const mockedGet = vi.mocked(logsApi.get);

const summary: LogSummary = {
  id: "log-01",
  source_id: "pedidos-api",
  parent_type: "API",
  entrada: "POST /pedidos",
  resultado: "200 OK",
  metodo: "POST",
  tiempo_ms: 480,
  estado: "OK",
  fecha: "2026-01-01T10:00:00Z",
  connection_id: "conexion-01",
};

const connections: Connection[] = [
  {
    id: "conexion-01",
    name: "Principal",
    engine: "mariadb",
    host: "localhost",
    port: 3306,
    user: "root",
    database: "logmon",
  },
];

// Cuatro pasos con su `orden` correlativo, tal como los devuelve el backend.
const record: LogRecord = {
  ...summary,
  steps: [
    { orden: 1, tipo: "ENTRADA", contenido: "Recibe pedido", duration_ms: 5 },
    { orden: 2, tipo: "SALIDA", contenido: "Valida stock", duration_ms: 12 },
    { orden: 3, tipo: "SALIDA", contenido: "Genera respuesta", duration_ms: null },
    { orden: 4, tipo: "ERROR", contenido: "Timeout en pago", duration_ms: 340 },
  ],
};

describe("LogDetail", () => {

  beforeEach(() => {
    mockedGet.mockReset();
  });


  test("muestra un placeholder cuando no hay log seleccionado", () => {
    render(<LogDetail summary={null} connections={connections} />);

    expect(screen.getByText("Seleccioná un log de la tabla para ver sus pasos."))
      .toBeInTheDocument();
    expect(mockedGet).not.toHaveBeenCalled();
  });


  test("muestra los cuatro pasos del log, en orden", async () => {
    mockedGet.mockResolvedValue(record);

    const { container } = render(<LogDetail summary={summary} connections={connections} />);

    await waitFor(() => {
      expect(container.querySelectorAll(".steps__item")).toHaveLength(4);
    });

    const contenidos = Array.from(container.querySelectorAll(".steps__content"))
      .map((node) => node.textContent);

    expect(contenidos).toEqual([
      "Recibe pedido",
      "Valida stock",
      "Genera respuesta",
      "Timeout en pago",
    ]);

    expect(mockedGet).toHaveBeenCalledWith("log-01", "conexion-01");
  });


  test("un paso ERROR se pinta distinto de uno SALIDA", async () => {
    mockedGet.mockResolvedValue(record);

    const { container } = render(<LogDetail summary={summary} connections={connections} />);

    await waitFor(() => {
      expect(container.querySelectorAll(".steps__item")).toHaveLength(4);
    });

    const items = container.querySelectorAll(".steps__item");
    const salidaBadge = items[1].querySelector(".badge");
    const errorBadge = items[3].querySelector(".badge");

    expect(salidaBadge).toHaveClass("badge--ok");
    expect(errorBadge).toHaveClass("badge--error");
    expect(salidaBadge?.className).not.toEqual(errorBadge?.className);
  });


  test("muestra la duración de cada paso, o un guión si no la tiene", async () => {
    mockedGet.mockResolvedValue(record);

    render(<LogDetail summary={summary} connections={connections} />);

    await waitFor(() => {
      expect(screen.getByText("5 ms")).toBeInTheDocument();
    });

    expect(screen.getByText("12 ms")).toBeInTheDocument();
    expect(screen.getByText("340 ms")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

});

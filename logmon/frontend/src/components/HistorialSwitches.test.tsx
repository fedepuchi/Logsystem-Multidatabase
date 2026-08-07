import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    sourcesApi: { ...actual.sourcesApi, history: vi.fn() },
  };
});

import HistorialSwitches from "./HistorialSwitches";
import { ApiError, sourcesApi, type SourceHistory } from "../api/client";

const mockedHistory = vi.mocked(sourcesApi.history);

const historia: SourceHistory = {
  source: "ventas",
  connections: ["C1", "C2"],
  audit: [
    {
      id: 2,
      source_id: "ventas",
      from_connection_id: "C1",
      to_connection_id: "C2",
      status: "OK",
      detail: null,
      created_at: "2026-08-06T12:00:00Z",
    },
    {
      id: 1,
      source_id: "ventas",
      from_connection_id: "C2",
      to_connection_id: "C3",
      status: "ABORTED",
      detail: "el motor destino no respondió al ping",
      created_at: "2026-08-06T11:00:00Z",
    },
  ],
};

beforeEach(() => {
  mockedHistory.mockReset();
});

it("sin fuente elegida no consulta la API", () => {
  render(<HistorialSwitches source={null} />);

  expect(mockedHistory).not.toHaveBeenCalled();
  expect(screen.getByText(/Elegí una fuente/)).toBeInTheDocument();
});

it("muestra cada cambio con su origen y su destino", async () => {
  mockedHistory.mockResolvedValue(historia);

  render(<HistorialSwitches source="ventas" />);

  // Se consulta por filas: C1 y C2 aparecen también en el resumen de arriba.
  await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(3));
  const filas = screen.getAllByRole("row").slice(1);

  expect(filas[0]).toHaveTextContent("C1");
  expect(filas[0]).toHaveTextContent("C2");
  expect(filas[1]).toHaveTextContent("C3");
});

it("distingue un switch aplicado de uno abortado", async () => {
  mockedHistory.mockResolvedValue(historia);

  render(<HistorialSwitches source="ventas" />);

  await waitFor(() => expect(screen.getByText("aplicado")).toBeInTheDocument());
  expect(screen.getByText("abortado")).toBeInTheDocument();
});

it("muestra el motivo de un switch abortado", async () => {
  mockedHistory.mockResolvedValue(historia);

  render(<HistorialSwitches source="ventas" />);

  await waitFor(() =>
    expect(screen.getByText(/no respondió al ping/)).toBeInTheDocument(),
  );
});

it("resume en cuántas conexiones escribió la fuente", async () => {
  // Es lo que explica por qué el visor sigue mostrando los logs viejos.
  mockedHistory.mockResolvedValue(historia);

  render(<HistorialSwitches source="ventas" />);

  const resumen = await screen.findByText(/Escribió en/);
  expect(resumen).toHaveTextContent("2");
  expect(resumen).toHaveTextContent("C1, C2");
});

it("una fuente sin cambios no muestra una tabla vacía", async () => {
  mockedHistory.mockResolvedValue({ source: "nueva", connections: ["C1"], audit: [] });

  render(<HistorialSwitches source="nueva" />);

  await waitFor(() =>
    expect(screen.getByText(/todavía no cambió de motor/)).toBeInTheDocument(),
  );
});

it("informa el error en vez de quedarse cargando", async () => {
  mockedHistory.mockRejectedValue(new ApiError(500, null, "la metadata no responde"));

  render(<HistorialSwitches source="ventas" />);

  await waitFor(() =>
    expect(screen.getByText(/la metadata no responde/)).toBeInTheDocument(),
  );
});

import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    statsApi: { get: vi.fn() },
  };
});

import PanelMetricas from "./PanelMetricas";
import { ApiError, statsApi, type LogStats } from "../api/client";

const mockedGet = vi.mocked(statsApi.get);

const stats: LogStats = {
  generated_at: "2026-08-06T12:00:00Z",
  bucket_minutes: 60,
  total_logs: 120,
  error_count: 30,
  error_rate: 0.25,
  engines: [
    {
      engine: "postgres",
      connection_ids: ["C1"],
      total_logs: 100,
      error_count: 25,
      error_rate: 0.25,
      volume: [],
    },
    {
      engine: "redis",
      connection_ids: ["C5"],
      total_logs: 20,
      error_count: 5,
      error_rate: 0.25,
      volume: [],
    },
  ],
  unavailable: [],
};

beforeEach(() => {
  mockedGet.mockReset();
});

it("muestra los totales que devuelve el backend", async () => {
  mockedGet.mockResolvedValue(stats);

  render(<PanelMetricas />);

  await waitFor(() => expect(screen.getByText("120")).toBeInTheDocument());
  expect(screen.getByText("30")).toBeInTheDocument();
  // La tasa se repite en las tarjetas y en cada motor: acá interesa la global.
  expect(screen.getByText("Tasa de error").previousSibling).toHaveTextContent("25.0 %");
});

it("desglosa por motor", async () => {
  mockedGet.mockResolvedValue(stats);

  render(<PanelMetricas />);

  await waitFor(() => expect(screen.getByText("postgres")).toBeInTheDocument());
  expect(screen.getByText("redis")).toBeInTheDocument();
  expect(screen.getByText("100")).toBeInTheDocument();
});

it("avisa cuando un motor no respondió", async () => {
  // Sin el aviso, los totales se leerían como completos sin serlo.
  mockedGet.mockResolvedValue({ ...stats, unavailable: ["C3"] });

  render(<PanelMetricas />);

  await waitFor(() => expect(screen.getByText(/no respondió/)).toBeInTheDocument());
  expect(screen.getByText(/los excluyen/)).toBeInTheDocument();
});

it("sin logs no muestra una tabla vacía", async () => {
  mockedGet.mockResolvedValue({ ...stats, total_logs: 0, error_count: 0, engines: [] });

  render(<PanelMetricas />);

  await waitFor(() =>
    expect(screen.getByText(/Todavía no hay logs para medir/)).toBeInTheDocument(),
  );
});

it("informa el error en vez de quedarse cargando", async () => {
  mockedGet.mockRejectedValue(new ApiError(401, null, "Falta el header X-Admin-Key"));

  render(<PanelMetricas />);

  await waitFor(() =>
    expect(screen.getByText(/X-Admin-Key/)).toBeInTheDocument(),
  );
});

it("filtra por fuente cuando se le indica una", async () => {
  mockedGet.mockResolvedValue(stats);

  render(<PanelMetricas source="ventas" />);

  await waitFor(() => expect(mockedGet).toHaveBeenCalledWith("ventas"));
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    sourcesApi: { ...actual.sourcesApi, switch: vi.fn() },
  };
});

import SwitchControl from "./SwitchControl";
import { ApiError, sourcesApi, type Connection, type Source } from "../api/client";

const mockedSwitch = vi.mocked(sourcesApi.switch);

const fuente: Source = { name: "ventas", parent_type: "API", connection_id: "C1" };

const conexiones: Connection[] = [
  { id: "C1", name: "Postgres", engine: "postgres", host: "db", port: 5432, database: "logdb" },
  { id: "C2", name: "Mongo", engine: "mongo", host: "db", port: 27017, database: "logdb" },
] as Connection[];

function montar(source: Source = fuente) {
  const onSwitched = vi.fn();
  const onError = vi.fn();
  render(
    <SwitchControl
      source={source}
      connections={conexiones}
      onSwitched={onSwitched}
      onError={onError}
    />,
  );
  return { onSwitched, onError };
}

beforeEach(() => {
  mockedSwitch.mockReset();
});

it("no deja confirmar sin haber elegido destino", () => {
  montar({ ...fuente, connection_id: null });

  expect(screen.getByRole("button", { name: /Cambiar base/ })).toBeDisabled();
});

it("no deja confirmar el motor en el que ya está", () => {
  // Un switch a la misma conexión no es un cambio: haría un flip innecesario.
  montar();

  expect(screen.getByRole("button", { name: /Cambiar base/ })).toBeDisabled();
});

it("habilita el botón al elegir un destino distinto", async () => {
  montar();

  await userEvent.selectOptions(screen.getByRole("combobox"), "C2");

  expect(screen.getByRole("button", { name: /Cambiar base/ })).toBeEnabled();
});

it("manda la fuente y el destino elegidos", async () => {
  mockedSwitch.mockResolvedValue({
    message: "ok",
    source: { ...fuente, connection_id: "C2" },
  });
  const { onSwitched } = montar();

  await userEvent.selectOptions(screen.getByRole("combobox"), "C2");
  await userEvent.click(screen.getByRole("button", { name: /Cambiar base/ }));

  await waitFor(() => expect(mockedSwitch).toHaveBeenCalledWith("ventas", "C2"));
  expect(onSwitched).toHaveBeenCalled();
});

it("un switch abortado avisa y vuelve al motor original", async () => {
  // Es la garantía del validate-before-flip: si el destino no responde, la
  // fuente sigue donde estaba y el selector tiene que reflejarlo.
  mockedSwitch.mockRejectedValue(new ApiError(409, null, "el destino no respondió al ping"));
  const { onError, onSwitched } = montar();

  await userEvent.selectOptions(screen.getByRole("combobox"), "C2");
  await userEvent.click(screen.getByRole("button", { name: /Cambiar base/ }));

  await waitFor(() =>
    expect(onError).toHaveBeenCalledWith(expect.stringContaining("no respondió al ping")),
  );
  expect(onSwitched).not.toHaveBeenCalled();
  expect(screen.getByRole("combobox")).toHaveValue("C1");
});

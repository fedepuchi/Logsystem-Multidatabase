import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    connectionsApi: { ...actual.connectionsApi, create: vi.fn(), test: vi.fn() },
  };
});

import ConnectionForm from "./ConnectionForm";
import { ApiError, connectionsApi, type Connection } from "../api/client";

const mockedCreate = vi.mocked(connectionsApi.create);
const mockedTest = vi.mocked(connectionsApi.test);

const creada = {
  id: "C9",
  name: "Postgres demo",
  engine: "postgres",
  host: "db",
  port: 5432,
  database: "logdb",
} as Connection;

beforeEach(() => {
  mockedCreate.mockReset();
  mockedTest.mockReset();
});

/** Los seis campos obligatorios. Con uno vacío el navegador bloquea el envío.
 *
 * Se limpia antes de escribir porque varios traen valor por defecto: `type`
 * concatena, así que sin el clear el host terminaba en "localhostdb".
 */
async function completarFormulario() {
  for (const [etiqueta, valor] of [
    [/Nombre/i, "Postgres demo"],
    [/Host/i, "db"],
    [/Usuario/i, "loguser"],
    [/Contraseña/i, "logpass"],
    [/Base de datos/i, "logdb"],
  ] as const) {
    const campo = screen.getByLabelText(etiqueta);
    await userEvent.clear(campo);
    await userEvent.type(campo, valor);
  }
}

it("los campos obligatorios están marcados como tales", () => {
  // La validación se apoya en el navegador: sin `required` el formulario se
  // enviaría vacío y el error llegaría recién desde la API.
  render(<ConnectionForm />);

  expect(screen.getByLabelText(/Nombre/i)).toBeRequired();
  expect(screen.getByLabelText(/Host/i)).toBeRequired();
  expect(screen.getByLabelText(/Base de datos/i)).toBeRequired();
});

it("no llama a la API si faltan campos obligatorios", async () => {
  render(<ConnectionForm />);

  await userEvent.click(screen.getByRole("button", { name: /Guardar conexión/i }));

  expect(mockedCreate).not.toHaveBeenCalled();
});

it("al enviar manda los datos cargados", async () => {
  mockedCreate.mockResolvedValue(creada);
  render(<ConnectionForm />);

  await completarFormulario();
  await userEvent.click(screen.getByRole("button", { name: /Guardar conexión/i }));

  await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
  expect(mockedCreate.mock.calls[0][0]).toMatchObject({
    name: "Postgres demo",
    host: "db",
    user: "loguser",
    database: "logdb",
  });
});

it("avisa cuando la creación falla y no limpia lo cargado", async () => {
  mockedCreate.mockRejectedValue(new ApiError(409, null, "Ya existe una conexión con ese nombre"));
  render(<ConnectionForm />);

  await completarFormulario();
  await userEvent.click(screen.getByRole("button", { name: /Guardar conexión/i }));

  await waitFor(() => expect(screen.getByText(/Ya existe una conexión/)).toBeInTheDocument());
  expect(screen.getByLabelText(/Nombre/i)).toHaveValue("Postgres demo");
});

it("notifica al padre cuando la conexión se creó", async () => {
  mockedCreate.mockResolvedValue(creada);
  const onCreated = vi.fn();
  render(<ConnectionForm onCreated={onCreated} />);

  await completarFormulario();
  await userEvent.click(screen.getByRole("button", { name: /Guardar conexión/i }));

  await waitFor(() => expect(onCreated).toHaveBeenCalledWith(creada));
});

it("probar la conexión informa el resultado real", async () => {
  mockedCreate.mockResolvedValue(creada);
  mockedTest.mockResolvedValue({ success: false, message: "no se pudo abrir el pool" });
  render(<ConnectionForm />);

  await completarFormulario();
  await userEvent.click(screen.getByRole("button", { name: /Guardar conexión/i }));
  await waitFor(() => expect(screen.getByText(/Conexión C9 creada/)).toBeInTheDocument());

  await userEvent.click(screen.getByRole("button", { name: /Test/i }));

  await waitFor(() =>
    expect(screen.getByText(/no se pudo abrir el pool/)).toBeInTheDocument(),
  );
});

import { render, screen } from "@testing-library/react";
import EstadoTabla from "./EstadoTabla";

describe("EstadoTabla", () => {

  test("muestra el mensaje de carga cuando loading es true", () => {
    render(<EstadoTabla loading />);

    expect(screen.getByText("Cargando logs..."))
      .toBeInTheDocument();
  });


  test("muestra el mensaje de vacio cuando no hay logs", () => {
    render(<EstadoTabla vacio />);

    expect(screen.getByText("No hay logs para los filtros aplicados."))
      .toBeInTheDocument();
  });


  test("muestra el error recibido", () => {
    render(<EstadoTabla error="Backend no disponible" />);

    expect(screen.getByText("Backend no disponible"))
      .toBeInTheDocument();
  });


  test("el error tiene precedencia sobre el mensaje de vacio", () => {
    render(<EstadoTabla vacio error="Backend no disponible" />);

    expect(screen.getByText("Backend no disponible"))
      .toBeInTheDocument();
    expect(screen.queryByText("No hay logs para los filtros aplicados."))
      .not.toBeInTheDocument();
  });


  test("la carga tiene precedencia sobre el error", () => {
    render(<EstadoTabla loading error="Backend no disponible" />);

    expect(screen.getByText("Cargando logs..."))
      .toBeInTheDocument();
    expect(screen.queryByText("Backend no disponible"))
      .not.toBeInTheDocument();
  });


  test("no renderiza nada si no aplica ningun estado", () => {
    const { container } = render(<EstadoTabla />);

    expect(container).toBeEmptyDOMElement();
  });

});

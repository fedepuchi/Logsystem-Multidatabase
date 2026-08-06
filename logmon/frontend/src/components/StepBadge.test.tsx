import { render, screen } from "@testing-library/react";
import StepBadge from "./StepBadge";

describe("StepBadge", () => {

  test("muestra el texto del tipo ENTRADA", () => {
    render(<StepBadge tipo="ENTRADA" />);

    expect(screen.getByText("ENTRADA"))
      .toBeInTheDocument();
  });


  test("muestra el texto del tipo SALIDA", () => {
    render(<StepBadge tipo="SALIDA" />);

    expect(screen.getByText("SALIDA"))
      .toBeInTheDocument();
  });


  test("muestra el texto del tipo ERROR", () => {
    render(<StepBadge tipo="ERROR" />);

    expect(screen.getByText("ERROR"))
      .toBeInTheDocument();
  });


  test("un paso ERROR se pinta distinto de uno SALIDA", () => {
    const { unmount } = render(<StepBadge tipo="SALIDA" />);
    const salidaBadge = screen.getByText("SALIDA");
    expect(salidaBadge).toHaveClass("badge", "badge--ok");
    expect(salidaBadge).not.toHaveClass("badge--error");
    unmount();

    render(<StepBadge tipo="ERROR" />);
    const errorBadge = screen.getByText("ERROR");
    expect(errorBadge).toHaveClass("badge", "badge--error");
    expect(errorBadge).not.toHaveClass("badge--ok");
  });


  test("ENTRADA y SALIDA comparten el mismo estilo (badge--ok)", () => {
    const { unmount } = render(<StepBadge tipo="ENTRADA" />);
    expect(screen.getByText("ENTRADA")).toHaveClass("badge--ok");
    unmount();

    render(<StepBadge tipo="SALIDA" />);
    expect(screen.getByText("SALIDA")).toHaveClass("badge--ok");
  });

});

import { render, screen } from "@testing-library/react";
import DbOriginBadge from "./DbOriginBadge"; 

describe("DbOriginBadge", () => {

  test("muestra sin origen si no hay connectionId", () => {
    render(<DbOriginBadge />);

    expect(screen.getByText("sin origen"))
      .toBeInTheDocument();
  });


  test("muestra conexión y motor MariaDB", () => {
    render(
      <DbOriginBadge
        connectionId="conexion-01"
        engine="mariadb"
      />
    );

    expect(
      screen.getByText("conexion-01 · MariaDB")
    ).toBeInTheDocument();
  });


  test("muestra solo conexión si no recibe engine", () => {
    render(
      <DbOriginBadge
        connectionId="conexion-02"
      />
    );

    expect(
      screen.getByText("conexion-02")
    ).toBeInTheDocument();
  });

});
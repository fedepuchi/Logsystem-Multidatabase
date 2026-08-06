interface EstadoTablaProps {
  loading?: boolean;
  vacio?: boolean;
  error?: string | null;
}

const MENSAJE_CARGANDO = "Cargando logs...";
const MENSAJE_VACIO = "No hay logs para los filtros aplicados.";
const MENSAJE_ERROR_GENERICO = "No se pudieron cargar los logs.";

export default function EstadoTabla({ loading, vacio, error }: EstadoTablaProps) {
  if (loading) {
    return (
      <p className="estado-tabla" role="status">
        {MENSAJE_CARGANDO}
      </p>
    );
  }

  if (error) {
    return (
      <p className="estado-tabla estado-tabla--error" role="alert">
        {error.trim() ? error : MENSAJE_ERROR_GENERICO}
      </p>
    );
  }

  if (vacio) {
    return (
      <p className="estado-tabla estado-tabla--vacio" role="status">
        {MENSAJE_VACIO}
      </p>
    );
  }

  return null;
}

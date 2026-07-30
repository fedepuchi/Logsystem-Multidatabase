import type { StepType } from "../api/client";

const CLASS_BY_TYPE: Record<StepType, string> = {
  ENTRADA: "badge badge--ok",
  SALIDA: "badge badge--ok",
  ERROR: "badge badge--error",
};

interface StepBadgeProps {
  tipo: StepType;
}

export default function StepBadge({ tipo }: StepBadgeProps) {
  return <span className={CLASS_BY_TYPE[tipo]}>{tipo}</span>;
}

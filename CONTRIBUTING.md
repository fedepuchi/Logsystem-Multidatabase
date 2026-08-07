# Cómo trabajar en este repo

Corto a propósito. Son las reglas que evitan que `main` se rompa con mucha gente
tocando el mismo código.

---

## Ramas

Una rama por tarea, con prefijo según qué es:

```
feat/    funcionalidad nueva      feat/paginacion-keyset
fix/     arreglo                  fix/auth-batch-stats
test/    sólo tests               test/formularios
docs/    sólo documentación       docs/readme-v2
ci/      workflows e infra        ci/arm64
```

Nunca se commitea directo a `main`.

---

## Antes de abrir el PR

**Correr los tests.** Los tres, según lo que hayas tocado:

```bash
cd logmon/backend && pytest -q
```

```bash
cd logmon/frontend && npm test && npx tsc --noEmit
```

Si tocaste adapters, router o la API, además hay que correrlos **contra los
motores reales**, porque si no se saltean sin avisar:

```bash
cd logmon && make up && make test-all
```

Eso necesita **8-10 GB de disco libre**. Si no los tenés, decilo en el PR: no
pasa nada, pero que quede escrito para que el revisor lo sepa.

---

## Qué tiene que llevar un PR

- **Sus tests.** Un arreglo sin un test que falle antes y pase después no está
  terminado: nada impide que vuelva.
- **Una descripción que explique el porqué**, no sólo el qué. El diff ya dice
  qué cambió; lo que hace falta es entender qué se rompía.
- **La evidencia**. Cuántos tests pasan, y qué **no** pudiste verificar. Esto
  último es lo más importante y lo que más se olvida.

---

## Definición de terminado

Un PR se mergea cuando:

1. **El CI está en verde.** Nada entra en rojo, y nada entra sin que el CI haya
   corrido. Un run encolado que nunca arrancó **no cuenta como verde**.
2. **Tiene la aprobación de Andrés Rueda**, el revisor asignado.
3. Los tests nuevos cubren el cambio.

---

## Archivos compartidos

Varias tareas se cruzan en los mismos archivos. Antes de tocar uno de estos,
avisá en el grupo:

| Archivo | Por qué |
|---|---|
| `storage/adapters/*.py` | Los tocan la paginación y la ingesta por lotes |
| `storage/router.py` | Igual |
| `pages/LogViewer.tsx` | Auto-refresco, paginación y filtros |
| `pages/Dashboard.tsx` | Historial de switches y panel de métricas |
| `api/client.ts` | Todos le agregan funciones |
| `metadata/repo.py`, `schema.sql` | Cifrado y API keys |

---

## Al revisar

Mirá tres cosas antes que el estilo:

- **¿Hay un test que falla sin el arreglo?** Si no, el arreglo no está probado.
- **¿Qué dice el autor que no pudo verificar?** Ahí suele estar el riesgo real.
- **¿El cambio toca una superficie que otro PR también toca?** Es de donde
  salieron los peores problemas: la ingesta por lotes quedó sin autenticación
  durante días porque se hizo en paralelo con el módulo de auth y nadie revisó
  la intersección al mergear.

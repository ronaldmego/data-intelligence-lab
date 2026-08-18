#!/usr/bin/env python3
"""Compara las dos orquestaciones con criterios fijados de antemano.

    python compare.py --runs 3

La pregunta "¿conviene que decida el código o el modelo?" se contesta midiendo,
no opinando. Las dos variantes corren sobre las mismas herramientas, el mismo
guard y la misma compuerta, así que lo que se compara es la conducta.

Los criterios se fijan **antes** de mirar los resultados:

1. **Orden.** ¿Consultó el catálogo antes de tocar el dato, en todas las corridas?
2. **Cobertura.** ¿Cuántas lecturas legítimas ofreció? En particular, ¿encontró
   la de `staff`? Es la que rompe el binario 500-contra-2: sin ella el informe
   parece un error de tipeo y no una ambigüedad.
3. **Exactitud.** Su SQL se vuelve a ejecutar contra la fuente y se compara con
   el número que reportó. Un agente que informa cifras que su propia consulta no
   devuelve es peor que uno que no responde.
4. **Reproducibilidad.** Dos corridas de la misma pregunta, ¿dan lo mismo?

El resultado se escribe como tabla y como JSON, para poder citarlo.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from guard import UnsafeQuery, check_query

PREGUNTA = "¿Cuántas tiendas tiene el negocio?"
CONCEPTO = "tienda"
ALIASES = ("store",)

#: La lectura que hace la diferencia entre "hay ambigüedad" y "hay un error".
LECTURA_CLAVE = "staff"


def _ports():
    from om_client import from_env as catalog_from_env
    from pg_client import from_env as sql_from_env

    return catalog_from_env(), sql_from_env()


def _resumen(plan, trace, sql_port) -> dict:
    inv = trace.to_dict()["invariants"]
    lecturas = []
    for c in plan.candidates:
        comprobado, nota = _recomprobar(c, sql_port)
        lecturas.append(
            {
                "etiqueta": c.label,
                "valor_reportado": c.value,
                "valor_recomprobado": comprobado,
                "coincide": comprobado == c.value if comprobado is not None else None,
                "nota": nota,
                "sql": c.sql,
            }
        )
    return {
        "orden_metadata_antes_de_sql": inv["metadata_before_sql"],
        "llamadas_metadata": inv["metadata_calls"],
        "llamadas_sql": inv["sql_calls"],
        "lecturas": lecturas,
        "valores": sorted({c.value for c in plan.candidates if c.value is not None}),
        "menciona_staff": any(
            LECTURA_CLAVE in (c.sql or "").lower() or LECTURA_CLAVE in c.label.lower()
            for c in plan.candidates
        ),
        "firma": sorted((c.label, c.value) for c in plan.candidates),
    }


def _recomprobar(candidate, sql_port) -> tuple[int | None, str]:
    """Ejecuta de nuevo el SQL que el agente dijo haber usado."""
    if not candidate.sql:
        return None, "no reportó SQL"
    try:
        check_query(candidate.sql)
    except UnsafeQuery as exc:
        return None, f"el guard rechaza su propio SQL: {exc.reason}"
    try:
        return sql_port.scalar(candidate.sql), ""
    except Exception as exc:
        return None, f"su SQL no vuelve a correr: {type(exc).__name__}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3, help="corridas por variante")
    ap.add_argument("--out", default="evidencia/comparacion.json")
    args = ap.parse_args(argv)

    from llm_orchestrator import run as run_llm
    from orchestrator import run as run_det

    resultados: dict[str, list[dict]] = {"deterministica": [], "llm": []}
    modelo = os.getenv("KIMI_MODEL", "kimi-k2.6")

    for i in range(args.runs):
        catalog, sql_port = _ports()
        try:
            _, plan, trace = run_det(
                PREGUNTA, catalog, sql_port, concept=CONCEPTO, aliases=ALIASES
            )
            resultados["deterministica"].append(_resumen(plan, trace, sql_port))
            print(f"  determinística {i + 1}/{args.runs} lista")
        finally:
            sql_port.close()
            catalog.close()

    for i in range(args.runs):
        catalog, sql_port = _ports()
        try:
            _, plan, trace = run_llm(PREGUNTA, catalog, sql_port, concept=CONCEPTO, aliases=ALIASES)
            resultados["llm"].append(_resumen(plan, trace, sql_port))
            print(f"  llm {i + 1}/{args.runs} lista")
        except Exception as exc:
            resultados["llm"].append({"error": f"{type(exc).__name__}: {exc}"})
            print(f"  llm {i + 1}/{args.runs} FALLÓ: {type(exc).__name__}")
        finally:
            sql_port.close()
            catalog.close()

    informe = _informe(resultados, modelo=modelo, runs=args.runs)
    print("\n" + informe)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(
            {"modelo": modelo, "corridas": args.runs, "resultados": resultados},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nDetalle en {args.out}")
    return 0


def _informe(resultados: dict, *, modelo: str, runs: int) -> str:
    filas = []
    for nombre, corridas in resultados.items():
        ok = [c for c in corridas if "error" not in c]
        if not ok:
            filas.append((nombre, "todas fallaron", "-", "-", "-", "-"))
            continue
        orden = sum(1 for c in ok if c["orden_metadata_antes_de_sql"])
        lecturas = sorted({len(c["lecturas"]) for c in ok})
        staff = sum(1 for c in ok if c["menciona_staff"])
        desajustes = sum(
            1 for c in ok for lec in c["lecturas"] if lec["coincide"] is not True
        )
        firmas = {json.dumps(c["firma"], ensure_ascii=False) for c in ok}
        filas.append(
            (
                nombre,
                f"{orden}/{len(ok)}",
                ",".join(str(x) for x in lecturas),
                f"{staff}/{len(ok)}",
                str(desajustes),
                "sí" if len(firmas) == 1 else f"no ({len(firmas)} distintas)",
            )
        )

    cab = ("variante", "orden ok", "lecturas", "halló staff", "cifras que no recomprueban", "idénticas")
    anchos = [max(len(str(f[i])) for f in (cab, *filas)) for i in range(len(cab))]
    linea = lambda f: "  ".join(str(f[i]).ljust(anchos[i]) for i in range(len(cab)))  # noqa: E731
    out = [
        f"COMPARACIÓN — {runs} corridas por variante · modelo {modelo}",
        "",
        linea(cab),
        "  ".join("-" * a for a in anchos),
    ]
    out.extend(linea(f) for f in filas)
    return "\n".join(out)


if __name__ == "__main__":
    raise SystemExit(main())

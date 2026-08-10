#!/usr/bin/env python3
"""Punto de entrada del POC.

    python run.py                       # reproduce la corrida capturada (sin servicios)
    python run.py --live                # contra OpenMetadata y PostgreSQL reales
    python run.py --live --capture out.json
    python run.py --mode llm --live     # deja que el modelo decida los pasos

Por omisión corre **offline** contra la captura versionada: quien clone el
repositorio ve el caso completo sin levantar nada. El modo vivo es para
regenerar la evidencia.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from fixture import RecordingCatalog, RecordingSql, load_capture, redact_host, save_capture
from report import build_answer, render_text

HERE = Path(__file__).resolve().parent
DEFAULT_FIXTURE = HERE / "fixtures" / "pagila-vanilla.json"
DEFAULT_QUESTION = "¿Cuántas tiendas tiene el negocio?"


def _live_ports():
    """Importa los adaptadores recién acá: el núcleo no depende de ellos."""
    from om_client import from_env as catalog_from_env
    from pg_client import from_env as sql_from_env

    return catalog_from_env(), sql_from_env()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--question", default=DEFAULT_QUESTION)
    ap.add_argument("--concept", default="tienda", help="cómo se nombra el concepto en la pregunta")
    ap.add_argument("--alias", action="append", default=["store"], help="otros nombres del concepto")
    ap.add_argument("--anchor", default=None, help="forzar la tabla ancla en vez de resolverla")
    ap.add_argument("--mode", choices=("deterministic", "llm"), default="deterministic")
    ap.add_argument("--live", action="store_true", help="usar los servicios reales")
    ap.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    ap.add_argument("--capture", default=None, help="guardar la corrida viva como captura")
    ap.add_argument("--trace", default=None, help="guardar el trace en este archivo")
    ap.add_argument("--json", dest="as_json", action="store_true", help="salida en JSON")
    args = ap.parse_args(argv)

    source: dict = {}
    if args.live:
        catalog, sql = _live_ports()
        source = {
            "openmetadata_url": redact_host(os.getenv("OPENMETADATA_URL", "")),
            "openmetadata_version": getattr(catalog, "version", lambda: "")(),
            "postgres": getattr(sql, "server_version", lambda: "")(),
        }
        if args.capture:
            catalog, sql = RecordingCatalog(catalog), RecordingSql(sql)
    else:
        if not Path(args.fixture).exists():
            print(
                f"no existe la captura {args.fixture}.\n"
                "Generala con:  python run.py --live --capture " + args.fixture,
                file=sys.stderr,
            )
            return 2
        catalog, sql, source = load_capture(args.fixture)

    aliases = tuple(dict.fromkeys(args.alias))

    if args.mode == "llm":
        from llm_orchestrator import run as run_llm

        governance, plan, trace = run_llm(
            args.question, catalog, sql, concept=args.concept, aliases=aliases
        )
    else:
        from orchestrator import run as run_deterministic

        governance, plan, trace = run_deterministic(
            args.question, catalog, sql, concept=args.concept, aliases=aliases, anchor=args.anchor
        )

    answer = build_answer(args.question, governance, plan)

    if args.as_json:
        salida = {"answer": answer.to_dict(), "trace": trace.to_dict()}
        print(json.dumps(salida, indent=2, ensure_ascii=False))
    else:
        print(render_text(answer))
        inv = trace.to_dict()["invariants"]
        print(
            f"Trace: {inv['metadata_calls']} llamadas de metadata · {inv['sql_calls']} de SQL · "
            f"metadata antes de SQL: {'sí' if inv['metadata_before_sql'] else 'NO'}"
        )
        if not args.live:
            print(f"Fuente: captura {Path(args.fixture).name} ({source.get('openmetadata_version', '?')})")

    if args.trace:
        Path(args.trace).parent.mkdir(parents=True, exist_ok=True)
        Path(args.trace).write_text(trace.to_json() + "\n", encoding="utf-8")
        print(f"Trace guardado en {args.trace}", file=sys.stderr)

    if args.live and args.capture:
        path = save_capture(args.capture, catalog=catalog, sql=sql, metadata=source)
        print(f"Captura guardada en {path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

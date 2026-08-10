#!/usr/bin/env python3
"""Comprueba las tres capas de solo lectura contra los servicios reales.

    python verify_readonly.py

Los tests de `tests/test_guard.py` cubren la capa 1, que es análisis de texto y
no necesita una base. Las capas 2 y 3 sólo se pueden demostrar contra el motor:
lo que se afirma es que PostgreSQL rechaza la escritura *aunque* el texto
hubiera pasado el análisis, y que el rol no tiene privilegio que ejercer.

Por eso este script manda las sentencias **salteando el guard**, a propósito. Es
la única forma de probar que las otras dos capas aguantan solas. Ninguna
escribe: todas mueren antes, que es exactamente lo que se está midiendo.
"""

from __future__ import annotations

import sys

from guard import UnsafeQuery, check_query
from pg_client import from_env

CONSULTAS_QUE_EL_GUARD_DEBE_FRENAR = [
    "SELECT 1;DROP TABLE public.store",
    "SELECT/**/1;DROP/**/TABLE/**/public.store",
    "SELECT * INTO nueva FROM public.store",
    "MERGE INTO public.store USING public.staff ON true WHEN MATCHED THEN DELETE",
    "CALL algun_proc()",
    "DO $$ BEGIN PERFORM 1; END $$",
    "REFRESH MATERIALIZED VIEW public.rental_by_category",
    "SELECT pg_sleep(600)",
]


def main() -> int:
    fallos = 0

    print("CAPA 1 — análisis de la sentencia (no necesita base)")
    for sql in CONSULTAS_QUE_EL_GUARD_DEBE_FRENAR:
        try:
            check_query(sql)
            print(f"  FALLÓ  permitió: {sql}")
            fallos += 1
        except UnsafeQuery as exc:
            print(f"  ok     {exc.reason:<55} | {sql[:52]}")

    sql_port = from_env()
    try:
        print(f"\n  motor: {sql_port.server_version()}")

        print("\nCAPAS 2 y 3 — el motor y el rol, con el guard salteado a propósito")
        for sentencia, resultado in sql_port.verify_read_only():
            marca = "FALLÓ " if resultado.startswith("PERMITIDA") else "ok    "
            if marca.strip() == "FALLÓ":
                fallos += 1
            print(f"  {marca} {sentencia[:58]:<58} -> {resultado[:90]}")

        print("\nCAPA 3 — privilegios efectivos del rol sobre public.store")
        for priv in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            tiene = sql_port.scalar(
                f"SELECT has_table_privilege(current_user, 'public.store', '{priv}')::int AS value"
            )
            esperado = 1 if priv == "SELECT" else 0
            marca = "ok    " if tiene == esperado else "FALLÓ "
            if tiene != esperado:
                fallos += 1
            print(f"  {marca} {priv:<9} = {'sí' if tiene else 'no'}")

        print("\nUna lectura legítima sigue funcionando")
        print(f"  store = {sql_port.scalar('SELECT count(*) AS value FROM public.store')} filas")
    finally:
        sql_port.close()

    print(f"\n{'TODO EN VERDE' if not fallos else f'{fallos} FALLOS'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())

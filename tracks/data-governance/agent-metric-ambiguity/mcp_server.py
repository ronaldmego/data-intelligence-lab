#!/usr/bin/env python3
"""Servidor MCP con las herramientas de solo lectura del POC.

    python mcp_server.py

Existe por continuidad con los dos proyectos hermanos del track
(`openmetadata-mcp-agent` y `agent-data-analyst`, ambos MCP): quien quiera
enchufar estas herramientas en Claude Desktop o en su propio asistente puede
hacerlo sin reimplementarlas.

**La corrida del POC no pasa por acá.** `run.py` llama a las mismas funciones
en proceso. Meter un proceso MCP en el camino de los tests agregaría una
frontera que no aporta evidencia y sí fragilidad en CI, donde además no hay
servicios que consultar.

Lo que se publica es un subconjunto estricto de lectura. No hay una herramienta
de escritura apagada por configuración: no está escrita.
"""

from __future__ import annotations

import json

from fastmcp import FastMCP

from guard import UnsafeQuery, check_query

mcp = FastMCP("metric-ambiguity-readonly")

_catalog = None
_sql = None


def _get_catalog():
    global _catalog
    if _catalog is None:
        from om_client import from_env

        _catalog = from_env()
    return _catalog


def _get_sql():
    global _sql
    if _sql is None:
        from pg_client import from_env

        _sql = from_env()
    return _sql


@mcp.tool
def list_glossary_terms() -> str:
    """Términos del glosario de negocio, con su definición.

    La primera pregunta ante una métrica: ¿alguien ya la definió?
    """
    terms = _get_catalog().list_glossary_terms()
    return json.dumps(
        [{"nombre": t.name, "fqn": t.fqn, "definicion": t.description} for t in terms],
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool
def search_tables(text: str, limit: int = 10) -> str:
    """Busca tablas del catálogo por texto libre."""
    hits = _get_catalog().search_tables(text, limit=limit)
    return json.dumps(
        [{"nombre": h.name, "fqn": h.fqn, "descripcion": h.description} for h in hits],
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool
def get_table(name: str) -> str:
    """Metadata de una tabla: descripción, owner, tier, dominio y columnas."""
    table = _get_catalog().get_table(name)
    if table is None:
        return json.dumps({"error": f"«{name}» no está en el catálogo"}, ensure_ascii=False)
    return json.dumps(
        {
            "nombre": table.name,
            "fqn": table.fqn,
            "schema": table.schema,
            "descripcion": table.description,
            "owners": list(table.owners),
            "tier": table.tier,
            "dominio": table.domain,
            "columnas": [
                {"nombre": c.name, "tipo": c.data_type, "descripcion": c.description}
                for c in table.columns
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool
def get_lineage(name: str) -> str:
    """Tablas conectadas aguas arriba y aguas abajo de una tabla."""
    catalog = _get_catalog()
    table = catalog.get_table(name)
    if table is None:
        return json.dumps({"error": f"«{name}» no está en el catálogo"}, ensure_ascii=False)
    lineage = catalog.get_lineage(table)
    return json.dumps(
        {"arriba": list(lineage.upstream), "abajo": list(lineage.downstream)},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool
def sql_scalar(sql: str) -> str:
    """Ejecuta una consulta de lectura de una sola sentencia que devuelve un número.

    Pasa por las tres capas: análisis de la sentencia, transacción de solo
    lectura y rol sin permisos de escritura.
    """
    try:
        check_query(sql)
    except UnsafeQuery as exc:
        return json.dumps({"error": f"consulta rechazada: {exc.reason}"}, ensure_ascii=False)
    try:
        return json.dumps({"valor": _get_sql().scalar(sql)}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()

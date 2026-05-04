#!/usr/bin/env python3
"""
OpenMetadata MCP Server
Permite interactuar con OpenMetadata via conversación natural.

Uso:
    python server.py

Requiere:
    - .env file con OPENMETADATA_URL y OPENMETADATA_TOKEN
    - O variables de entorno configuradas
"""

import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

# Cargar .env desde el directorio del script
load_dotenv(Path(__file__).parent / ".env")

# Configuración
OPENMETADATA_URL = os.getenv("OPENMETADATA_URL", "http://localhost:8585")
OPENMETADATA_TOKEN = os.getenv("OPENMETADATA_TOKEN", "")

# Crear servidor MCP
mcp = FastMCP("OpenMetadata")


def strip_html(text: str) -> str:
    """Remover tags HTML de descripciones de OpenMetadata."""
    return re.sub(r"<[^>]+>", "", text).strip()


def get_headers():
    """Headers de autenticación para OpenMetadata API"""
    return {
        "Authorization": f"Bearer {OPENMETADATA_TOKEN}",
        "Content-Type": "application/json"
    }

def api_get(endpoint: str, params: dict = None) -> dict:
    """Hacer GET request a OpenMetadata API"""
    url = f"{OPENMETADATA_URL}/api/v1{endpoint}"
    try:
        response = httpx.get(url, headers=get_headers(), params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 404:
            raise ValueError(f"No encontrado en OpenMetadata (404): {endpoint}")
        elif status == 401:
            raise ValueError("Token de autenticación inválido o expirado (401)")
        elif status == 500:
            raise ValueError("Error interno del servidor OpenMetadata (500)")
        else:
            raise ValueError(f"Error HTTP {status}: {e.response.text[:200]}")
    except httpx.TimeoutException:
        raise ValueError(f"Timeout: OpenMetadata tardó más de 30 segundos ({url})")
    except httpx.ConnectError:
        raise ValueError(f"No se pudo conectar a OpenMetadata en {OPENMETADATA_URL}")


@mcp.tool
def search_catalog(query: str, limit: int = 10) -> str:
    """Buscar assets en el catálogo de datos.

    Args:
        query: Término de búsqueda (ej: "customers", "ventas", "pipeline")
        limit: Máximo de resultados a retornar

    Returns:
        Lista de assets que coinciden con la búsqueda
    """
    try:
        result = api_get("/search/query", {"q": query, "size": limit})
        hits = result.get("hits", {}).get("hits", [])

        if not hits:
            return f"No se encontraron resultados para '{query}'"

        output = [f"Encontrados {len(hits)} resultados para '{query}':\n"]
        for hit in hits:
            source = hit.get("_source", {})
            name = source.get("name", "Sin nombre")
            entity_type = source.get("entityType", "unknown")
            fqn = source.get("fullyQualifiedName", "")
            desc = strip_html(source.get("description", "Sin descripción"))[:100]
            output.append(f"- [{entity_type}] {name}\n  FQN: {fqn}\n  {desc}")

        return "\n".join(output)
    except Exception as e:
        return f"Error buscando en catálogo: {str(e)}"


@mcp.tool
def list_tables(database: str = None, schema: str = None, limit: int = 20) -> str:
    """Listar tablas del catálogo de datos.

    Args:
        database: Filtrar por nombre de database (opcional)
        schema: Filtrar por nombre de schema (opcional)
        limit: Máximo de tablas a retornar

    Returns:
        Lista de tablas con su descripción
    """
    try:
        params = {"limit": limit}
        if database:
            params["database"] = database

        result = api_get("/tables", params)
        tables = result.get("data", [])

        if not tables:
            return "No se encontraron tablas"

        # Filtrar por schema si se especifica
        if schema:
            tables = [t for t in tables if schema.lower() in t.get("fullyQualifiedName", "").lower()]

        output = [f"Encontradas {len(tables)} tablas:\n"]
        for t in tables:
            name = t.get("name", "")
            fqn = t.get("fullyQualifiedName", "")
            desc = strip_html(t.get("description", "Sin descripción"))[:80]
            columns = len(t.get("columns", []))
            output.append(f"- {name} ({columns} columnas)\n  FQN: {fqn}\n  {desc}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listando tablas: {str(e)}"


@mcp.tool
def get_table_details(table_name: str) -> str:
    """Obtener detalles completos de una tabla.

    Args:
        table_name: Nombre o FQN de la tabla

    Returns:
        Detalles de la tabla incluyendo columnas, owner, tags
    """
    try:
        # Primero buscar la tabla
        search_result = api_get("/search/query", {"q": table_name, "size": 1})
        hits = search_result.get("hits", {}).get("hits", [])

        if not hits:
            return f"No se encontró la tabla '{table_name}'"

        # Obtener ID y hacer request de detalles
        table_id = hits[0]["_source"].get("id")
        if not table_id:
            return f"No se pudo obtener ID de la tabla '{table_name}'"

        table = api_get(f"/tables/{table_id}")

        # Formatear respuesta
        # Resolver owner: OM reciente usa "owners" (lista), versiones legacy usan "owner" (singular)
        owners_list = table.get("owners", [])
        if owners_list:
            owner_str = ", ".join(o.get("displayName", o.get("name", "?")) for o in owners_list)
        else:
            legacy = table.get("owner", {})
            owner_str = legacy.get("displayName", legacy.get("name", "Sin owner"))

        output = [
            f"📊 Tabla: {table.get('name')}",
            f"FQN: {table.get('fullyQualifiedName')}",
            f"Descripción: {strip_html(table.get('description', 'Sin descripción'))}",
            f"Owner: {owner_str}",
            "",
            f"📋 Columnas ({len(table.get('columns', []))}):"
        ]

        for col in table.get("columns", [])[:20]:  # Limitar a 20 columnas
            col_name = col.get("name", "")
            col_type = col.get("dataType", "")
            col_desc = strip_html(col.get("description", ""))[:50]
            output.append(f"  - {col_name} ({col_type}): {col_desc}")

        if len(table.get("columns", [])) > 20:
            output.append(f"  ... y {len(table.get('columns', [])) - 20} columnas más")

        # Tags
        tags = table.get("tags", [])
        if tags:
            tag_names = [t.get("tagFQN", "") for t in tags]
            output.append(f"\n🏷️ Tags: {', '.join(tag_names)}")

        return "\n".join(output)
    except Exception as e:
        return f"Error obteniendo detalles: {str(e)}"


@mcp.tool
def get_lineage(asset_name: str) -> str:
    """Obtener el linaje (upstream/downstream) de un asset.

    Args:
        asset_name: Nombre o FQN del asset (tabla, pipeline, etc.)

    Returns:
        Información de linaje mostrando de dónde vienen los datos y a dónde van
    """
    try:
        # Buscar el asset
        search_result = api_get("/search/query", {"q": asset_name, "size": 1})
        hits = search_result.get("hits", {}).get("hits", [])

        if not hits:
            return f"No se encontró el asset '{asset_name}'"

        source = hits[0]["_source"]
        entity_type = source.get("entityType", "table")
        entity_id = source.get("id")

        # Obtener linaje
        lineage = api_get(f"/lineage/{entity_type}/{entity_id}")

        nodes = lineage.get("nodes", [])
        edges = lineage.get("edges", [])

        if not edges:
            return f"No hay linaje registrado para '{asset_name}'"

        # Encontrar upstream y downstream
        upstream = []
        downstream = []

        for edge in edges:
            from_id = edge.get("fromEntity", {}).get("id")
            to_id = edge.get("toEntity", {}).get("id")

            if to_id == entity_id:
                # Es upstream
                from_node = next((n for n in nodes if n.get("id") == from_id), {})
                upstream.append(from_node.get("fullyQualifiedName", from_id))
            elif from_id == entity_id:
                # Es downstream
                to_node = next((n for n in nodes if n.get("id") == to_id), {})
                downstream.append(to_node.get("fullyQualifiedName", to_id))

        output = [f"🔗 Linaje de: {asset_name}\n"]

        if upstream:
            output.append("⬆️ Upstream (fuentes):")
            for u in upstream:
                output.append(f"  ← {u}")
        else:
            output.append("⬆️ Upstream: Ninguno (es fuente original)")

        output.append("")

        if downstream:
            output.append("⬇️ Downstream (destinos):")
            for d in downstream:
                output.append(f"  → {d}")
        else:
            output.append("⬇️ Downstream: Ninguno (es destino final)")

        return "\n".join(output)
    except Exception as e:
        return f"Error obteniendo linaje: {str(e)}"


@mcp.tool
def list_databases() -> str:
    """Listar todas las databases/services registrados.

    Returns:
        Lista de databases con su tipo y descripción
    """
    try:
        result = api_get("/databases", {"limit": 50})
        databases = result.get("data", [])

        if not databases:
            return "No hay databases registradas"

        output = [f"🗄️ Databases registradas ({len(databases)}):\n"]
        for db in databases:
            name = db.get("name", "")
            service = db.get("service", {}).get("name", "")
            desc = db.get("description", "Sin descripción")[:60]
            output.append(f"- {name} (servicio: {service})\n  {desc}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listando databases: {str(e)}"


@mcp.tool
def list_glossaries(limit: int = 20) -> str:
    """Listar glosarios raíz disponibles en el catálogo.

    Args:
        limit: Máximo de glosarios a retornar

    Returns:
        Lista de glosarios con su nombre, descripción y conteo de términos
    """
    try:
        result = api_get("/glossaries", {"limit": limit})
        glossaries = result.get("data", [])

        if not glossaries:
            return "No hay glosarios disponibles"

        output = [f"📚 Glosarios disponibles ({len(glossaries)}):\n"]
        for g in glossaries:
            name = g.get("name", "")
            fqn = g.get("fullyQualifiedName", name)
            definition = strip_html(g.get("description", ""))[:120] or "Sin descripción"
            term_count = g.get("termCount") or len(g.get("children", []) or [])
            output.append(f"- {name} (FQN: {fqn}, {term_count} términos)\n  {definition}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listando glosarios: {str(e)}"


@mcp.tool
def list_glossary_terms(glossary: str = None, limit: int = 50) -> str:
    """Listar términos del glosario de negocio mostrando jerarquía completa.

    La salida agrupa términos por glosario raíz y, dentro de cada uno, muestra
    parent terms (con sus hijos anidados) y leaf terms (sin hijos).

    Args:
        glossary: Filtrar por nombre o FQN de glosario raíz (opcional)
        limit: Máximo de términos a retornar

    Returns:
        Árbol jerárquico de términos con FQN, definición y sinónimos
    """
    try:
        params = {
            "limit": limit,
            "fields": "parent,glossary,children,fullyQualifiedName",
        }
        result = api_get("/glossaryTerms", params)
        terms = result.get("data", [])

        # Filtrar por nombre o FQN del glosario raíz (client-side, evita resolver UUID)
        if glossary:
            terms = [
                t for t in terms
                if (t.get("glossary") or {}).get("name") == glossary
                or (t.get("glossary") or {}).get("fullyQualifiedName") == glossary
            ]

        if not terms:
            return "No hay términos de glosario"

        # Indexar por FQN para resolver hijos
        by_fqn = {t.get("fullyQualifiedName"): t for t in terms if t.get("fullyQualifiedName")}

        # Agrupar por glosario raíz; separar parent terms (sin parent) de leaf
        by_root: dict[str, list] = {}
        for t in terms:
            root = (t.get("glossary") or {}).get("name") or "Sin glosario"
            by_root.setdefault(root, []).append(t)

        def format_term(t: dict, indent: int = 0) -> list[str]:
            pad = "  " * indent
            name = t.get("name", "")
            fqn = t.get("fullyQualifiedName", name)
            definition = strip_html(t.get("description", ""))[:100] or "Sin definición"
            synonyms = t.get("synonyms", []) or []
            syn_str = f" — sinónimos: {', '.join(synonyms)}" if synonyms else ""
            children_refs = t.get("children", []) or []
            child_count = len(children_refs)
            child_label = f" [parent term, {child_count} hijos]" if child_count else ""
            lines = [f"{pad}- {name} (FQN: {fqn}){child_label}{syn_str}"]
            lines.append(f"{pad}  {definition}")
            # Anidar hijos si están presentes en el batch
            for ref in children_refs:
                child = by_fqn.get(ref.get("fullyQualifiedName"))
                if child:
                    lines.extend(format_term(child, indent + 1))
            return lines

        output = [f"📖 Términos de glosario ({len(terms)}, agrupados por raíz):\n"]
        for root, root_terms in sorted(by_root.items()):
            output.append(f"\n📚 {root}")
            # Solo formatear top-level (sin parent term) para no duplicar
            for t in root_terms:
                if not t.get("parent"):
                    output.extend(format_term(t, indent=1))
            # Términos huérfanos (parent fuera del batch): mostrarlos al final
            top_fqns = {t.get("fullyQualifiedName") for t in root_terms if not t.get("parent")}
            shown_children = set()
            def collect_children(t: dict):
                for ref in (t.get("children") or []):
                    fqn = ref.get("fullyQualifiedName")
                    if fqn:
                        shown_children.add(fqn)
                        child = by_fqn.get(fqn)
                        if child:
                            collect_children(child)
            for t in root_terms:
                if not t.get("parent"):
                    collect_children(t)
            orphans = [
                t for t in root_terms
                if t.get("fullyQualifiedName") not in top_fqns
                and t.get("fullyQualifiedName") not in shown_children
            ]
            if orphans:
                output.append("  (huérfanos — parent fuera del batch:)")
                for t in orphans:
                    output.extend(format_term(t, indent=1))

        return "\n".join(output)
    except Exception as e:
        return f"Error listando glosario: {str(e)}"


if __name__ == "__main__":
    if not OPENMETADATA_TOKEN:
        print("⚠️  ADVERTENCIA: OPENMETADATA_TOKEN no está configurado")
        print("   Exporta la variable: export OPENMETADATA_TOKEN='tu-token'")
        print("")

    print("🚀 Iniciando OpenMetadata MCP Server")
    print(f"   URL: {OPENMETADATA_URL}")
    print(f"   Token: {'✅ Configurado' if OPENMETADATA_TOKEN else '❌ No configurado'}")
    print("")
    mcp.run()

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
import json
from pathlib import Path
from dotenv import load_dotenv
from fastmcp import FastMCP
import httpx

# Cargar .env desde el directorio del script
load_dotenv(Path(__file__).parent / ".env")

# Configuración
OPENMETADATA_URL = os.getenv("OPENMETADATA_URL", "http://localhost:8585")
OPENMETADATA_TOKEN = os.getenv("OPENMETADATA_TOKEN", "")

# Crear servidor MCP
mcp = FastMCP("OpenMetadata")

def get_headers():
    """Headers de autenticación para OpenMetadata API"""
    return {
        "Authorization": f"Bearer {OPENMETADATA_TOKEN}",
        "Content-Type": "application/json"
    }

def api_get(endpoint: str, params: dict = None) -> dict:
    """Hacer GET request a OpenMetadata API"""
    url = f"{OPENMETADATA_URL}/api/v1{endpoint}"
    response = httpx.get(url, headers=get_headers(), params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def api_patch(endpoint: str, operations: list) -> dict:
    """Hacer PATCH request a OpenMetadata API usando JSON Patch (RFC 6902)"""
    url = f"{OPENMETADATA_URL}/api/v1{endpoint}"
    headers = get_headers()
    headers["Content-Type"] = "application/json-patch+json"
    response = httpx.patch(url, headers=headers, json=operations, timeout=30)
    response.raise_for_status()
    return response.json()


def strip_html(text: str) -> str:
    """Remover tags HTML de un string"""
    return re.sub(r"<[^>]+>", "", text).strip()


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
def list_tables(database: str = None, schema_name: str = None, limit: int = 20) -> str:
    """Listar tablas del catálogo de datos.

    Args:
        database: Filtrar por nombre de database (opcional)
        schema_name: Filtrar por nombre de schema (opcional)
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
        if schema_name:
            tables = [t for t in tables if schema_name.lower() in t.get("fullyQualifiedName", "").lower()]

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
        output = [
            f"📊 Tabla: {table.get('name')}",
            f"FQN: {table.get('fullyQualifiedName')}",
            f"Descripción: {strip_html(table.get('description', 'Sin descripción'))}",
            f"Owner: {table.get('owner', {}).get('name', 'Sin owner')}",
            f"",
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
            desc = strip_html(db.get("description", "Sin descripción"))[:60]
            output.append(f"- {name} (servicio: {service})\n  {desc}")
        
        return "\n".join(output)
    except Exception as e:
        return f"Error listando databases: {str(e)}"


@mcp.tool
def list_glossary_terms(glossary: str = None, limit: int = 20) -> str:
    """Listar términos del glosario de negocio.
    
    Args:
        glossary: Nombre del glosario específico (opcional)
        limit: Máximo de términos a retornar
    
    Returns:
        Lista de términos con su definición
    """
    try:
        result = api_get("/glossaryTerms", {"limit": limit})
        terms = result.get("data", [])
        
        if not terms:
            return "No hay términos de glosario"
        
        output = [f"📖 Términos de glosario ({len(terms)}):\n"]
        for term in terms:
            name = term.get("name", "")
            definition = strip_html(term.get("description", "Sin definición"))[:100]
            synonyms = term.get("synonyms", [])
            syn_str = f" (sinónimos: {', '.join(synonyms)})" if synonyms else ""
            output.append(f"- {name}{syn_str}\n  {definition}")
        
        return "\n".join(output)
    except Exception as e:
        return f"Error listando glosario: {str(e)}"


@mcp.tool
def list_domains(limit: int = 50) -> str:
    """Listar dominios y subdominios de datos del catálogo.

    Args:
        limit: Máximo de dominios a retornar

    Returns:
        Lista de dominios con tipo, descripción y subdominios
    """
    try:
        result = api_get("/domains", {"limit": limit})
        domains = result.get("data", [])

        if not domains:
            return "No hay dominios registrados"

        output = [f"🏛️ Dominios registrados ({len(domains)}):\n"]
        for d in domains:
            name = d.get("name", "")
            display = d.get("displayName", name)
            domain_type = d.get("domainType", "")
            desc = strip_html(d.get("description", "Sin descripción"))[:100]
            parent = d.get("parent", {})
            parent_name = parent.get("name", "") if parent else ""
            parent_str = f" (sub-dominio de: {parent_name})" if parent_name else ""
            output.append(f"- {display}{parent_str}\n  Tipo: {domain_type}\n  {desc}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listando dominios: {str(e)}"


@mcp.tool
def update_table_description(table_name: str, description: str) -> str:
    """Actualizar la descripción de una tabla en OpenMetadata.

    Args:
        table_name: Nombre o FQN de la tabla
        description: Nueva descripción para la tabla

    Returns:
        Confirmación del cambio o mensaje de error
    """
    try:
        search_result = api_get("/search/query", {"q": table_name, "size": 1})
        hits = search_result.get("hits", {}).get("hits", [])

        if not hits:
            return f"No se encontró la tabla '{table_name}'"

        table_id = hits[0]["_source"].get("id")
        fqn = hits[0]["_source"].get("fullyQualifiedName", table_name)
        if not table_id:
            return f"No se pudo obtener ID de la tabla '{table_name}'"

        operations = [{"op": "add", "path": "/description", "value": description}]
        api_patch(f"/tables/{table_id}", operations)

        return f"Descripción de '{fqn}' actualizada a: {description}"
    except httpx.HTTPStatusError as e:
        return f"Error HTTP actualizando tabla: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error actualizando descripción de tabla: {str(e)}"


@mcp.tool
def update_column_description(table_name: str, column_name: str, description: str) -> str:
    """Actualizar la descripción de una columna en una tabla de OpenMetadata.

    Args:
        table_name: Nombre o FQN de la tabla
        column_name: Nombre de la columna a actualizar
        description: Nueva descripción para la columna

    Returns:
        Confirmación del cambio o mensaje de error
    """
    try:
        search_result = api_get("/search/query", {"q": table_name, "size": 1})
        hits = search_result.get("hits", {}).get("hits", [])

        if not hits:
            return f"No se encontró la tabla '{table_name}'"

        table_id = hits[0]["_source"].get("id")
        fqn = hits[0]["_source"].get("fullyQualifiedName", table_name)
        if not table_id:
            return f"No se pudo obtener ID de la tabla '{table_name}'"

        table = api_get(f"/tables/{table_id}")
        columns = table.get("columns", [])

        col_index = None
        for i, col in enumerate(columns):
            if col.get("name", "").lower() == column_name.lower():
                col_index = i
                break

        if col_index is None:
            available = [col.get("name", "") for col in columns]
            return (
                f"Columna '{column_name}' no encontrada en '{fqn}'. "
                f"Columnas disponibles: {', '.join(available)}"
            )

        operations = [{"op": "add", "path": f"/columns/{col_index}/description", "value": description}]
        api_patch(f"/tables/{table_id}", operations)

        return (
            f"Descripción de columna '{column_name}' en '{fqn}' "
            f"actualizada a: {description}"
        )
    except httpx.HTTPStatusError as e:
        return f"Error HTTP actualizando columna: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error actualizando descripción de columna: {str(e)}"


@mcp.tool
def list_users(limit: int = 50) -> str:
    """Listar usuarios registrados en OpenMetadata.

    Args:
        limit: Máximo de usuarios a retornar

    Returns:
        Lista de usuarios con nombre y email
    """
    try:
        result = api_get("/users", {"limit": limit, "isBot": False})
        users = result.get("data", [])

        if not users:
            return "No hay usuarios registrados"

        output = [f"👤 Usuarios registrados ({len(users)}):\n"]
        for u in users:
            name = u.get("name", "")
            display = u.get("displayName", name)
            email = u.get("email", "")
            output.append(f"- {display} ({name})\n  Email: {email}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listando usuarios: {str(e)}"


@mcp.tool
def list_teams(limit: int = 50) -> str:
    """Listar equipos registrados en OpenMetadata.

    Args:
        limit: Máximo de equipos a retornar

    Returns:
        Lista de equipos con nombre y descripción
    """
    try:
        result = api_get("/teams", {"limit": limit})
        teams = result.get("data", [])

        if not teams:
            return "No hay equipos registrados"

        output = [f"👥 Equipos registrados ({len(teams)}):\n"]
        for t in teams:
            name = t.get("name", "")
            display = t.get("displayName", name)
            desc = strip_html(t.get("description", "Sin descripción"))[:80]
            team_type = t.get("teamType", "")
            output.append(f"- {display} ({name})\n  Tipo: {team_type}\n  {desc}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listando equipos: {str(e)}"


@mcp.tool
def assign_owner(table_name: str, owner_name: str, owner_type: str = "user") -> str:
    """Asignar un owner (usuario o equipo) a una tabla en OpenMetadata.

    Args:
        table_name: Nombre o FQN de la tabla
        owner_name: Nombre del usuario o equipo a asignar como owner
        owner_type: Tipo de owner: "user" o "team"

    Returns:
        Confirmación del cambio o mensaje de error
    """
    try:
        if owner_type not in ("user", "team"):
            return f"owner_type debe ser 'user' o 'team', recibido: '{owner_type}'"

        # Find owner by name
        endpoint = "/users" if owner_type == "user" else "/teams"
        try:
            owner = api_get(f"{endpoint}/name/{owner_name}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # List available options for guidance
                available = api_get(endpoint, {"limit": 50})
                names = [item.get("name", "") for item in available.get("data", [])]
                entity_label = "usuarios" if owner_type == "user" else "equipos"
                return (
                    f"{owner_type.capitalize()} '{owner_name}' no encontrado. "
                    f"{entity_label.capitalize()} disponibles: {', '.join(names)}"
                )
            raise

        owner_id = owner.get("id")

        # Find table
        search_result = api_get("/search/query", {"q": table_name, "size": 1})
        hits = search_result.get("hits", {}).get("hits", [])

        if not hits:
            return f"No se encontró la tabla '{table_name}'"

        table_id = hits[0]["_source"].get("id")
        fqn = hits[0]["_source"].get("fullyQualifiedName", table_name)
        if not table_id:
            return f"No se pudo obtener ID de la tabla '{table_name}'"

        operations = [{"op": "add", "path": "/owners", "value": [{"id": owner_id, "type": owner_type}]}]
        api_patch(f"/tables/{table_id}", operations)

        owner_display = owner.get("displayName", owner_name)
        return f"Owner de '{fqn}' asignado a: {owner_display} ({owner_type})"
    except httpx.HTTPStatusError as e:
        return f"Error HTTP asignando owner: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error asignando owner: {str(e)}"


if __name__ == "__main__":
    if not OPENMETADATA_TOKEN:
        print("⚠️  ADVERTENCIA: OPENMETADATA_TOKEN no está configurado")
        print("   Exporta la variable: export OPENMETADATA_TOKEN='tu-token'")
        print("")
    
    print(f"🚀 Iniciando OpenMetadata MCP Server")
    print(f"   URL: {OPENMETADATA_URL}")
    print(f"   Token: {'✅ Configurado' if OPENMETADATA_TOKEN else '❌ No configurado'}")
    print("")
    mcp.run()

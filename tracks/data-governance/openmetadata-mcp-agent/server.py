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
OPENMETADATA_URL = os.getenv("OPENMETADATA_URL", "http://localhost:8585").rstrip("/")
OPENMETADATA_TOKEN = os.getenv("OPENMETADATA_TOKEN", "")
VERIFY_SSL = os.getenv("OPENMETADATA_VERIFY_SSL", "true").lower() != "false"

# HTTP client con configuración SSL
http_client = httpx.Client(verify=VERIFY_SSL, timeout=30)

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
    response = http_client.get(url, headers=get_headers(), params=params)
    response.raise_for_status()
    return response.json()


def api_patch(endpoint: str, operations: list) -> dict:
    """Hacer PATCH request a OpenMetadata API usando JSON Patch (RFC 6902)"""
    url = f"{OPENMETADATA_URL}/api/v1{endpoint}"
    headers = get_headers()
    headers["Content-Type"] = "application/json-patch+json"
    response = http_client.patch(url, headers=headers, json=operations)
    response.raise_for_status()
    return response.json()


def api_post(endpoint: str, payload: dict) -> dict:
    """Hacer POST request a OpenMetadata API"""
    url = f"{OPENMETADATA_URL}/api/v1{endpoint}"
    response = http_client.post(url, headers=get_headers(), json=payload)
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
        
        table = api_get(f"/tables/{table_id}", {"fields": "owners,tags,columns"})
        
        # Resolve owner(s) — API v1 uses "owners" (list)
        owners_list = table.get("owners", [])
        if owners_list:
            owner_names = ", ".join(o.get("displayName", o.get("name", "?")) for o in owners_list)
        else:
            # Fallback to legacy singular "owner"
            owner_names = table.get("owner", {}).get("displayName", table.get("owner", {}).get("name", "Sin owner"))
        
        # Formatear respuesta
        output = [
            f"📊 Tabla: {table.get('name')}",
            f"FQN: {table.get('fullyQualifiedName')}",
            f"Descripción: {strip_html(table.get('description', 'Sin descripción'))}",
            f"Owner: {owner_names}",
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
def list_stored_procedures(limit: int = 50) -> str:
    """Listar stored procedures registrados en OpenMetadata.

    Args:
        limit: Máximo de stored procedures a retornar

    Returns:
        Lista de stored procedures con nombre, database y descripción
    """
    try:
        result = api_get("/storedProcedures", {"limit": limit})
        procedures = result.get("data", [])

        if not procedures:
            return "No hay stored procedures registrados"

        output = [f"⚙️ Stored Procedures ({len(procedures)}):\n"]
        for sp in procedures:
            name = sp.get("name", "")
            fqn = sp.get("fullyQualifiedName", "")
            desc = strip_html(sp.get("description", "Sin descripción"))[:80]
            db_schema = sp.get("databaseSchema", {}).get("name", "")
            output.append(f"- {name}\n  FQN: {fqn}\n  Schema: {db_schema}\n  {desc}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listando stored procedures: {str(e)}"


@mcp.tool
def list_policies(limit: int = 50) -> str:
    """Listar políticas de acceso en OpenMetadata.

    Args:
        limit: Máximo de políticas a retornar

    Returns:
        Lista de políticas con nombre, descripción y reglas
    """
    try:
        result = api_get("/policies", {"limit": limit})
        policies = result.get("data", [])

        if not policies:
            return "No hay políticas registradas"

        output = [f"📜 Políticas ({len(policies)}):\n"]
        for p in policies:
            name = p.get("name", "")
            display = p.get("displayName", name)
            desc = strip_html(p.get("description", "Sin descripción"))[:80]
            rules_count = len(p.get("rules", []))
            output.append(f"- {display}\n  Nombre: {name}\n  Reglas: {rules_count}\n  {desc}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listando políticas: {str(e)}"


@mcp.tool
def list_roles(limit: int = 50) -> str:
    """Listar roles definidos en OpenMetadata.

    Args:
        limit: Máximo de roles a retornar

    Returns:
        Lista de roles con nombre, descripción y políticas asociadas
    """
    try:
        result = api_get("/roles", {"limit": limit})
        roles = result.get("data", [])

        if not roles:
            return "No hay roles registrados"

        output = [f"🔑 Roles ({len(roles)}):\n"]
        for r in roles:
            name = r.get("name", "")
            display = r.get("displayName", name)
            desc = strip_html(r.get("description", "Sin descripción"))[:80]
            policies = [pol.get("name", "") for pol in r.get("policies", [])]
            policies_str = f" (políticas: {', '.join(policies)})" if policies else ""
            output.append(f"- {display}{policies_str}\n  Nombre: {name}\n  {desc}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listando roles: {str(e)}"


@mcp.tool
def list_services(service_type: str = "database", limit: int = 50) -> str:
    """Listar servicios registrados en OpenMetadata.

    Args:
        service_type: Tipo de servicio: "database", "messaging", "dashboard", "pipeline", "mlmodel", "storage", "search"
        limit: Máximo de servicios a retornar

    Returns:
        Lista de servicios con nombre, tipo y descripción
    """
    try:
        type_map = {
            "database": "databaseServices",
            "messaging": "messagingServices",
            "dashboard": "dashboardServices",
            "pipeline": "pipelineServices",
            "mlmodel": "mlmodelServices",
            "storage": "storageServices",
            "search": "searchServices",
        }
        endpoint = type_map.get(service_type)
        if not endpoint:
            return f"Tipo de servicio no válido: '{service_type}'. Opciones: {', '.join(type_map.keys())}"

        result = api_get(f"/services/{endpoint}", {"limit": limit})
        services = result.get("data", [])

        if not services:
            return f"No hay servicios de tipo '{service_type}' registrados"

        output = [f"🔌 Servicios de {service_type} ({len(services)}):\n"]
        for s in services:
            name = s.get("name", "")
            svc_type = s.get("serviceType", "")
            desc = strip_html(s.get("description", "Sin descripción"))[:80]
            output.append(f"- {name}\n  Tipo: {svc_type}\n  {desc}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listando servicios: {str(e)}"


@mcp.tool
def list_pipelines(limit: int = 50) -> str:
    """Listar pipelines de datos registrados en OpenMetadata.

    Args:
        limit: Máximo de pipelines a retornar

    Returns:
        Lista de pipelines con nombre, servicio y descripción
    """
    try:
        result = api_get("/pipelines", {"limit": limit})
        pipelines = result.get("data", [])

        if not pipelines:
            return "No hay pipelines registrados"

        output = [f"🔄 Pipelines ({len(pipelines)}):\n"]
        for p in pipelines:
            name = p.get("name", "")
            fqn = p.get("fullyQualifiedName", "")
            desc = strip_html(p.get("description", "Sin descripción"))[:80]
            service = p.get("service", {}).get("name", "")
            output.append(f"- {name}\n  FQN: {fqn}\n  Servicio: {service}\n  {desc}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listando pipelines: {str(e)}"


@mcp.tool
def list_dashboards(limit: int = 50) -> str:
    """Listar dashboards registrados en OpenMetadata.

    Args:
        limit: Máximo de dashboards a retornar

    Returns:
        Lista de dashboards con nombre, servicio y descripción
    """
    try:
        result = api_get("/dashboards", {"limit": limit})
        dashboards = result.get("data", [])

        if not dashboards:
            return "No hay dashboards registrados"

        output = [f"📊 Dashboards ({len(dashboards)}):\n"]
        for d in dashboards:
            name = d.get("name", "")
            fqn = d.get("fullyQualifiedName", "")
            display = d.get("displayName", name)
            desc = strip_html(d.get("description", "Sin descripción"))[:80]
            service = d.get("service", {}).get("name", "")
            output.append(f"- {display}\n  FQN: {fqn}\n  Servicio: {service}\n  {desc}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listando dashboards: {str(e)}"


@mcp.tool
def list_topics(limit: int = 50) -> str:
    """Listar topics (Kafka/mensajería) registrados en OpenMetadata.

    Args:
        limit: Máximo de topics a retornar

    Returns:
        Lista de topics con nombre, servicio y descripción
    """
    try:
        result = api_get("/topics", {"limit": limit})
        topics = result.get("data", [])

        if not topics:
            return "No hay topics registrados"

        output = [f"📨 Topics ({len(topics)}):\n"]
        for t in topics:
            name = t.get("name", "")
            fqn = t.get("fullyQualifiedName", "")
            desc = strip_html(t.get("description", "Sin descripción"))[:80]
            service = t.get("service", {}).get("name", "")
            partitions = t.get("partitions", 0)
            output.append(f"- {name}\n  FQN: {fqn}\n  Servicio: {service}\n  Particiones: {partitions}\n  {desc}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listando topics: {str(e)}"


@mcp.tool
def list_data_products(limit: int = 50) -> str:
    """Listar data products registrados en OpenMetadata.

    Args:
        limit: Máximo de data products a retornar

    Returns:
        Lista de data products con nombre, dominio y descripción
    """
    try:
        result = api_get("/dataProducts", {"limit": limit})
        products = result.get("data", [])

        if not products:
            return "No hay data products registrados"

        output = [f"📦 Data Products ({len(products)}):\n"]
        for dp in products:
            name = dp.get("name", "")
            fqn = dp.get("fullyQualifiedName", "")
            display = dp.get("displayName", name)
            desc = strip_html(dp.get("description", "Sin descripción"))[:80]
            domain = dp.get("domain", {}).get("name", "Sin dominio")
            output.append(f"- {display}\n  FQN: {fqn}\n  Dominio: {domain}\n  {desc}")

        return "\n".join(output)
    except Exception as e:
        return f"Error listando data products: {str(e)}"


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


@mcp.tool
def create_glossary(name: str, description: str, display_name: str = None) -> str:
    """Crear un nuevo glosario en OpenMetadata.

    Args:
        name: Nombre del glosario (sin espacios, usar guiones)
        description: Descripción del glosario
        display_name: Nombre para mostrar (opcional, usa name si no se especifica)

    Returns:
        Confirmación de creación o mensaje de error
    """
    try:
        payload = {
            "name": name,
            "displayName": display_name or name,
            "description": description,
        }
        result = api_post("/glossaries", payload)
        fqn = result.get("fullyQualifiedName", name)
        return f"Glosario '{fqn}' creado exitosamente"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return f"Ya existe un glosario con el nombre '{name}'"
        return f"Error HTTP creando glosario: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error creando glosario: {str(e)}"


@mcp.tool
def create_glossary_term(
    glossary_name: str,
    term_name: str,
    description: str,
    synonyms: list[str] = None,
) -> str:
    """Crear un nuevo término en un glosario de OpenMetadata.

    Args:
        glossary_name: Nombre o FQN del glosario donde agregar el término
        term_name: Nombre del término (sin espacios, usar guiones)
        description: Definición del término
        synonyms: Lista de sinónimos opcionales

    Returns:
        Confirmación de creación o mensaje de error
    """
    try:
        # Verify glossary exists
        try:
            api_get(f"/glossaries/name/{glossary_name}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                available = api_get("/glossaries", {"limit": 50})
                names = [g.get("name", "") for g in available.get("data", [])]
                if names:
                    return (
                        f"Glosario '{glossary_name}' no encontrado. "
                        f"Glosarios disponibles: {', '.join(names)}"
                    )
                return f"Glosario '{glossary_name}' no encontrado. No hay glosarios creados."
            raise

        payload = {
            "name": term_name,
            "description": description,
            "glossary": glossary_name,
        }
        if synonyms:
            payload["synonyms"] = synonyms

        result = api_post("/glossaryTerms", payload)
        fqn = result.get("fullyQualifiedName", term_name)
        syn_str = f" (sinónimos: {', '.join(synonyms)})" if synonyms else ""
        return f"Término '{fqn}' creado exitosamente{syn_str}"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return f"Ya existe un término '{term_name}' en el glosario '{glossary_name}'"
        return f"Error HTTP creando término: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error creando término de glosario: {str(e)}"


@mcp.tool
def link_glossary_term(table_name: str, term_fqn: str) -> str:
    """Vincular un término de glosario a una tabla como tag.

    Args:
        table_name: Nombre o FQN de la tabla
        term_fqn: FQN del término de glosario (ej: "mi-glosario.mi-termino")

    Returns:
        Confirmación del vínculo o mensaje de error
    """
    try:
        # Find table
        search_result = api_get("/search/query", {"q": table_name, "size": 1})
        hits = search_result.get("hits", {}).get("hits", [])

        if not hits:
            return f"No se encontró la tabla '{table_name}'"

        table_id = hits[0]["_source"].get("id")
        table_fqn = hits[0]["_source"].get("fullyQualifiedName", table_name)
        if not table_id:
            return f"No se pudo obtener ID de la tabla '{table_name}'"

        # Verify the glossary term exists
        try:
            api_get(f"/glossaryTerms/name/{term_fqn}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return f"Término de glosario '{term_fqn}' no encontrado. Usa el formato 'glosario.termino'."
            raise

        operations = [{
            "op": "add",
            "path": "/tags/0",
            "value": {
                "tagFQN": term_fqn,
                "source": "Glossary",
                "labelType": "Manual",
            },
        }]
        api_patch(f"/tables/{table_id}", operations)

        return f"Término '{term_fqn}' vinculado a la tabla '{table_fqn}'"
    except httpx.HTTPStatusError as e:
        return f"Error HTTP vinculando término: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error vinculando término de glosario: {str(e)}"


@mcp.tool
def create_classification(name: str, description: str) -> str:
    """Crear una nueva clasificación (categoría de tags) en OpenMetadata.

    Args:
        name: Nombre de la clasificación (sin espacios, usar guiones)
        description: Descripción de la clasificación

    Returns:
        Confirmación de creación o mensaje de error
    """
    try:
        result = api_post("/classifications", {"name": name, "description": description})
        return f"Clasificación '{result.get('name')}' creada exitosamente"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return f"Ya existe una clasificación con el nombre '{name}'"
        return f"Error HTTP creando clasificación: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error creando clasificación: {str(e)}"


@mcp.tool
def create_tag(classification_name: str, tag_name: str, description: str) -> str:
    """Crear un nuevo tag dentro de una clasificación en OpenMetadata.

    Args:
        classification_name: Nombre de la clasificación donde crear el tag
        tag_name: Nombre del tag (sin espacios, usar guiones)
        description: Descripción del tag

    Returns:
        Confirmación de creación o mensaje de error
    """
    try:
        # Verify classification exists
        try:
            api_get(f"/classifications/name/{classification_name}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                available = api_get("/classifications", {"limit": 50})
                names = [c.get("name", "") for c in available.get("data", [])]
                return (
                    f"Clasificación '{classification_name}' no encontrada. "
                    f"Clasificaciones disponibles: {', '.join(names)}"
                )
            raise

        payload = {
            "name": tag_name,
            "description": description,
            "classification": classification_name,
        }
        result = api_post("/tags", payload)
        fqn = result.get("fullyQualifiedName", f"{classification_name}.{tag_name}")
        return f"Tag '{fqn}' creado exitosamente"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return f"Ya existe un tag '{tag_name}' en la clasificación '{classification_name}'"
        return f"Error HTTP creando tag: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error creando tag: {str(e)}"


@mcp.tool
def assign_tag(table_name: str, tag_fqn: str) -> str:
    """Asignar un tag a una tabla en OpenMetadata.

    Args:
        table_name: Nombre o FQN de la tabla
        tag_fqn: FQN del tag (ej: "mi-clasificacion.mi-tag")

    Returns:
        Confirmación de la asignación o mensaje de error
    """
    try:
        # Find table
        search_result = api_get("/search/query", {"q": table_name, "size": 1})
        hits = search_result.get("hits", {}).get("hits", [])

        if not hits:
            return f"No se encontró la tabla '{table_name}'"

        table_id = hits[0]["_source"].get("id")
        table_fqn = hits[0]["_source"].get("fullyQualifiedName", table_name)
        if not table_id:
            return f"No se pudo obtener ID de la tabla '{table_name}'"

        # Verify tag exists
        try:
            api_get(f"/tags/name/{tag_fqn}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return f"Tag '{tag_fqn}' no encontrado. Usa el formato 'clasificacion.tag'."
            raise

        operations = [{
            "op": "add",
            "path": "/tags/0",
            "value": {
                "tagFQN": tag_fqn,
                "source": "Classification",
                "labelType": "Manual",
            },
        }]
        api_patch(f"/tables/{table_id}", operations)

        return f"Tag '{tag_fqn}' asignado a la tabla '{table_fqn}'"
    except httpx.HTTPStatusError as e:
        return f"Error HTTP asignando tag: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error asignando tag: {str(e)}"


@mcp.tool
def create_domain(name: str, description: str, domain_type: str = "Aggregate") -> str:
    """Crear un nuevo dominio de datos en OpenMetadata.

    Args:
        name: Nombre del dominio (sin espacios, usar guiones)
        description: Descripción del dominio
        domain_type: Tipo de dominio: "Aggregate", "Consumer Aligned", o "Source Aligned"

    Returns:
        Confirmación de creación o mensaje de error
    """
    try:
        valid_types = ("Aggregate", "Consumer Aligned", "Source Aligned")
        if domain_type not in valid_types:
            return f"domain_type debe ser uno de: {', '.join(valid_types)}"

        payload = {
            "name": name,
            "description": description,
            "domainType": domain_type,
        }
        result = api_post("/domains", payload)
        fqn = result.get("fullyQualifiedName", name)
        return f"Dominio '{fqn}' creado exitosamente (tipo: {domain_type})"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return f"Ya existe un dominio con el nombre '{name}'"
        return f"Error HTTP creando dominio: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error creando dominio: {str(e)}"


# ===========================================================================
# DATA QUALITY TOOLS
# ===========================================================================

@mcp.tool
def list_test_suites(limit: int = 50) -> str:
    """Listar test suites de calidad de datos con resumen de resultados.

    Args:
        limit: Máximo de resultados

    Returns:
        Lista de test suites con conteo de tests passed/failed/aborted
    """
    try:
        result = api_get("/dataQuality/testSuites", {"limit": limit, "fields": "summary"})
        suites = result.get("data", [])
        if not suites:
            return "No se encontraron test suites configurados."
        output = [f"Test Suites ({len(suites)}):\n"]
        for s in suites:
            name = s.get("name", "")
            description = strip_html(s.get("description", ""))
            summary = s.get("summary", {})
            total = summary.get("total", 0)
            success = summary.get("success", 0)
            failed = summary.get("failed", 0)
            aborted = summary.get("aborted", 0)
            status_icon = "✅" if failed == 0 and total > 0 else ("❌" if failed > 0 else "⚪")
            line = f"{status_icon} {name}: {total} tests ({success} passed, {failed} failed, {aborted} aborted)"
            if description:
                line += f"\n   {description}"
            output.append(line)
        return "\n".join(output)
    except httpx.HTTPStatusError as e:
        return f"Error HTTP listando test suites: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error listando test suites: {str(e)}"


@mcp.tool
def list_test_cases(table_fqn: str = None, status: str = None, limit: int = 50) -> str:
    """Listar test cases de calidad de datos con su último resultado.

    Args:
        table_fqn: FQN de la tabla para filtrar (ej: "service.db.schema.table"). Opcional.
        status: Filtrar por estado: "Success", "Failed", "Aborted". Opcional.
        limit: Máximo de resultados

    Returns:
        Lista de test cases con estado, tipo, y última ejecución
    """
    try:
        params = {"limit": limit, "fields": "testDefinition,testSuite,testCaseResult"}
        if table_fqn:
            params["entityLink"] = f"<#E::table::{table_fqn}>"
            params["includeAllTests"] = "true"

        result = api_get("/dataQuality/testCases", params)
        cases = result.get("data", [])

        if status:
            cases = [
                c for c in cases
                if c.get("testCaseResult", {}).get("testCaseStatus", "").lower() == status.lower()
            ]

        if not cases:
            msg = "No se encontraron test cases"
            if table_fqn:
                msg += f" para la tabla '{table_fqn}'"
            if status:
                msg += f" con estado '{status}'"
            return msg + "."

        output = [f"Test Cases ({len(cases)}):\n"]
        for tc in cases:
            name = tc.get("name", "")
            test_def = tc.get("testDefinition", {}).get("name", "N/A")
            tc_result = tc.get("testCaseResult", {})
            tc_status = tc_result.get("testCaseStatus", "N/A")
            result_msg = tc_result.get("result", "")
            ts = tc_result.get("timestamp", 0)

            status_icon = {"Success": "✅", "Failed": "❌", "Aborted": "⚠️"}.get(tc_status, "⚪")
            line = f"{status_icon} [{tc_status}] {name}\n   Tipo: {test_def}"
            if result_msg:
                line += f"\n   Resultado: {result_msg}"
            if ts:
                from datetime import datetime, timezone
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                line += f"\n   Última ejecución: {dt}"
            output.append(line)

        return "\n".join(output)
    except httpx.HTTPStatusError as e:
        return f"Error HTTP listando test cases: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error listando test cases: {str(e)}"


@mcp.tool
def get_failed_tests(limit: int = 50) -> str:
    """Obtener todos los test cases que están fallando actualmente.

    Args:
        limit: Máximo de resultados

    Returns:
        Lista de tests fallidos con tabla afectada, tipo de test y mensaje de fallo
    """
    try:
        result = api_get("/dataQuality/testCases", {
            "limit": limit,
            "testCaseStatus": "Failed",
            "fields": "testDefinition,testSuite,testCaseResult",
        })
        cases = result.get("data", [])

        if not cases:
            return "No hay tests fallando actualmente. ✅"

        output = [f"Tests fallando ({len(cases)}):\n"]
        for tc in cases:
            name = tc.get("name", "")
            fqn = tc.get("fullyQualifiedName", "")
            test_def = tc.get("testDefinition", {}).get("name", "N/A")
            suite = tc.get("testSuite", {}).get("name", "N/A")
            tc_result = tc.get("testCaseResult", {})
            result_msg = tc_result.get("result", "")
            ts = tc_result.get("timestamp", 0)

            line = f"❌ {name}\n   Tipo: {test_def} | Suite: {suite}"
            if fqn:
                # Extraer tabla del FQN (todo menos el último segmento)
                table_path = ".".join(fqn.split(".")[:-1])
                line += f"\n   Tabla: {table_path}"
            if result_msg:
                line += f"\n   Fallo: {result_msg}"
            if ts:
                from datetime import datetime, timezone
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                line += f"\n   Detectado: {dt}"
            output.append(line)

        return "\n".join(output)
    except httpx.HTTPStatusError as e:
        return f"Error HTTP obteniendo tests fallidos: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error obteniendo tests fallidos: {str(e)}"


@mcp.tool
def get_test_case_results(test_case_fqn: str, days: int = 7) -> str:
    """Obtener el historial de resultados de un test case específico.

    Args:
        test_case_fqn: FQN del test case (ej: "service.db.schema.table.test_name")
        days: Días de historial a consultar (default 7)

    Returns:
        Historial de ejecuciones con estado, resultado y timestamp
    """
    try:
        import time
        from datetime import datetime, timezone

        end_ts = int(time.time() * 1000)
        start_ts = end_ts - (days * 86400 * 1000)

        result = api_get(
            f"/dataQuality/testCases/{test_case_fqn}/testCaseResult",
            {"startTs": start_ts, "endTs": end_ts, "limit": 30},
        )
        results = result.get("data", [])

        if not results:
            return f"No hay resultados en los últimos {days} días para '{test_case_fqn}'."

        output = [f"Historial de '{test_case_fqn}' (últimos {days} días, {len(results)} ejecuciones):\n"]
        for r in results:
            tc_status = r.get("testCaseStatus", "N/A")
            result_msg = r.get("result", "")
            ts = r.get("timestamp", 0)
            test_values = r.get("testResultValue", [])

            status_icon = {"Success": "✅", "Failed": "❌", "Aborted": "⚠️"}.get(tc_status, "⚪")
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if ts else "N/A"
            line = f"{status_icon} {dt} — {tc_status}"
            if result_msg:
                line += f"\n   {result_msg}"
            if test_values:
                vals = ", ".join(f"{v.get('name')}={v.get('value')}" for v in test_values)
                line += f"\n   Valores: {vals}"
            output.append(line)

        return "\n".join(output)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Test case no encontrado: '{test_case_fqn}'"
        if e.response.status_code == 500:
            return f"El test case '{test_case_fqn}' aún no tiene ejecuciones registradas. Ejecuta el test suite primero."
        return f"Error HTTP obteniendo resultados: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error obteniendo resultados del test case: {str(e)}"


if __name__ == "__main__":
    if not OPENMETADATA_TOKEN:
        print("⚠️  ADVERTENCIA: OPENMETADATA_TOKEN no está configurado")
        print("   Exporta la variable: export OPENMETADATA_TOKEN='tu-token'")
        print("")
    
    print(f"🚀 Iniciando OpenMetadata MCP Server")
    print(f"   URL: {OPENMETADATA_URL}")
    print(f"   SSL verify: {'✅ Enabled' if VERIFY_SSL else '⚠️  Disabled'}")
    print(f"   Token: {'✅ Configurado' if OPENMETADATA_TOKEN else '❌ No configurado'}")
    print("")
    mcp.run()

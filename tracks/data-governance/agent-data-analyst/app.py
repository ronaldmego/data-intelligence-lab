#!/usr/bin/env python3
"""
Khipu Analytics - Super Analista de Datos con IA
Interfaz conversacional para explorar y describir datos.
Dual MCP: OpenMetadata (catálogo) + SQL (queries directas).
"""

import os
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

# Cargar configuración
load_dotenv(Path(__file__).parent / ".env")

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# Importar tools del MCP de OpenMetadata (catálogo)
from server import (
    search_catalog,
    list_tables,
    get_table_details,
    list_databases,
    list_glossary_terms,
    get_lineage
)

# Importar tools del MCP SQL (queries directas)
from sql_server import (
    execute_query,
    list_schemas,
    describe_table,
    get_column_stats,
    get_table_profile
)

# Configuración
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
OPENMETADATA_URL = os.getenv("OPENMETADATA_URL", "http://localhost:8585")

# Info de herramientas para el LLM
TOOLS_INFO = """
Herramientas disponibles para explorar datos. Tienes DOS fuentes:

📚 CATÁLOGO (OpenMetadata) - Entiende qué datos existen y cómo están gobernados:
1. search_catalog(query) - Buscar assets por término (tablas, pipelines, etc.)
2. list_tables(limit) - Listar tablas disponibles con su esquema
3. get_table_details(table_name) - Ver columnas, owner, tags de una tabla
4. list_databases() - Ver todas las bases de datos registradas
5. get_lineage(asset_name) - Ver el linaje de datos (origen y destino)
6. list_glossary_terms() - Ver términos del glosario de negocio

🔍 SQL DIRECTO - Ejecuta queries para describir los datos reales:
7. list_schemas() - Listar schemas disponibles con cantidad de tablas
8. describe_table(schema_name, table_name) - Estructura: columnas, tipos, nullables, row count
9. get_column_stats(schema_name, table_name, column_name) - Stats de una columna: min/max/avg/median/std para numéricas, top frecuencias para categóricas
10. get_table_profile(schema_name, table_name) - Perfil rápido de TODA la tabla: stats de cada columna
11. execute_query(sql) - Ejecutar query SELECT personalizada (solo lectura)

ESTRATEGIA: Usa el catálogo para entender contexto y gobernanza. Usa SQL para explorar datos reales.
"""

def init_llm():
    """Inicializar el modelo de Gemini"""
    return ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        temperature=0
    )

def agent_process(query: str, llm) -> str:
    """Procesar query del usuario usando el agente"""
    
    # Paso 1: Decidir qué herramienta usar
    decision_prompt = f"""Eres un asistente de Data Governance experto. Analiza la pregunta del usuario y decide qué herramienta usar.

{TOOLS_INFO}

Pregunta: "{query}"

Responde SOLO con:
FUNCTION: nombre_de_funcion
PARAMS: parametro=valor

Ejemplos:
- Listar tablas del catálogo: FUNCTION: list_tables, PARAMS: limit=15
- Buscar assets: FUNCTION: search_catalog, PARAMS: query=término
- Detalles de tabla (catálogo): FUNCTION: get_table_details, PARAMS: table_name=nombre_tabla
- Bases de datos: FUNCTION: list_databases, PARAMS: none
- Linaje: FUNCTION: get_lineage, PARAMS: asset_name=nombre
- Glosario: FUNCTION: list_glossary_terms, PARAMS: none
- Listar schemas SQL: FUNCTION: list_schemas, PARAMS: none
- Estructura de tabla SQL: FUNCTION: describe_table, PARAMS: schema_name=telco_demo, table_name=customers
- Perfil completo de tabla: FUNCTION: get_table_profile, PARAMS: schema_name=telco_demo, table_name=customers
- Stats de una columna: FUNCTION: get_column_stats, PARAMS: schema_name=telco_demo, table_name=customers, column_name=city
- Query personalizada: FUNCTION: execute_query, PARAMS: sql=SELECT COUNT(*) FROM telco_demo.customers
"""

    decision_response = llm.invoke([HumanMessage(content=decision_prompt)])
    decision = decision_response.content.strip()
    
    # Helper para extraer parámetros
    def get_param(name, default=""):
        if f"{name}=" in decision:
            return decision.split(f"{name}=")[1].split("\n")[0].split(",")[0].strip()
        return default
    
    # Paso 2: Ejecutar la herramienta
    try:
        # --- Catálogo (OpenMetadata) ---
        if "list_tables" in decision:
            limit = int(get_param("limit", "15"))
            result = list_tables(limit=limit)
            
        elif "search_catalog" in decision:
            result = search_catalog(get_param("query", query), limit=10)
            
        elif "get_table_details" in decision:
            table_name = get_param("table_name")
            result = get_table_details(table_name) if table_name else "Falta nombre de tabla"
            
        elif "list_databases" in decision:
            result = list_databases()
            
        elif "get_lineage" in decision:
            asset_name = get_param("asset_name")
            result = get_lineage(asset_name) if asset_name else "Falta nombre del asset"
            
        elif "list_glossary_terms" in decision:
            result = list_glossary_terms()
        
        # --- SQL Directo ---
        elif "get_table_profile" in decision:
            schema = get_param("schema_name")
            table = get_param("table_name")
            result = get_table_profile(schema, table) if schema and table else "Faltan schema_name y table_name"
            
        elif "get_column_stats" in decision:
            schema = get_param("schema_name")
            table = get_param("table_name")
            column = get_param("column_name")
            result = get_column_stats(schema, table, column) if all([schema, table, column]) else "Faltan parámetros"
            
        elif "describe_table" in decision:
            schema = get_param("schema_name")
            table = get_param("table_name")
            result = describe_table(schema, table) if schema and table else "Faltan schema_name y table_name"
            
        elif "list_schemas" in decision:
            result = list_schemas()
            
        elif "execute_query" in decision:
            sql = get_param("sql")
            result = execute_query(sql) if sql else "Falta la query SQL"
            
        else:
            result = "No pude determinar qué herramienta usar para esta pregunta."
            
    except Exception as e:
        result = f"Error ejecutando la consulta: {str(e)}"
    
    # Paso 3: Formatear respuesta natural
    format_prompt = f"""Eres Khipu Analytics, un Super Analista de Datos. Basándote en los datos obtenidos, responde la pregunta del usuario de forma clara y útil.

Pregunta del usuario: "{query}"

Datos obtenidos:
{result}

Instrucciones:
- Responde en español
- Sé conciso pero informativo
- Si hay datos numéricos, resalta los insights más interesantes (Top 3, % relevantes, anomalías)
- Si hay muchos resultados, resume los más relevantes
- Si no hay resultados, sugiere alternativas
- Usa formato markdown para mejor legibilidad
- Cuando muestres stats, interpreta: no solo números, sino qué significan
"""

    final_response = llm.invoke([HumanMessage(content=format_prompt)])
    return final_response.content

# ============== STREAMLIT UI ==============

st.set_page_config(
    page_title="Khipu Analytics",
    page_icon="📊",
    layout="wide"
)

# Header
st.title("📊 Khipu Analytics")
st.caption(f"Super Analista de Datos con IA | Catálogo: `{OPENMETADATA_URL}` | SQL: directo")

# Sidebar con info
with st.sidebar:
    st.header("ℹ️ Acerca de")
    st.markdown("""
    **Khipu Analytics** — Super Analista de Datos con IA.
    
    Combina catálogo gobernado (OpenMetadata) con 
    queries SQL directas para entender tus datos.
    
    **Ejemplos de preguntas:**
    - ¿Qué tablas tenemos?
    - Dame el perfil de la tabla customers
    - ¿Qué schemas hay disponibles?
    - Estadísticas de la columna city en customers
    - ¿De dónde vienen los datos de orders?
    - ¿Cuántos clientes activos hay?
    """)
    
    st.divider()
    
    st.header("⚙️ Configuración")
    st.text(f"Modelo: {GEMINI_MODEL}")
    st.text(f"OpenMetadata: {OPENMETADATA_URL}")
    
    st.divider()
    
    if st.button("🗑️ Limpiar chat"):
        st.session_state.messages = []
        st.rerun()

# Inicializar historial de chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# Inicializar LLM
if "llm" not in st.session_state:
    try:
        st.session_state.llm = init_llm()
    except Exception as e:
        st.error(f"Error inicializando Gemini: {e}")
        st.stop()

# Mostrar historial de mensajes
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input del usuario
if prompt := st.chat_input("Pregunta sobre tu catálogo de datos..."):
    # Agregar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Generar respuesta
    with st.chat_message("assistant"):
        with st.spinner("Consultando catálogo..."):
            try:
                response = agent_process(prompt, st.session_state.llm)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                error_msg = f"❌ Error: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

#!/usr/bin/env python3
"""
OpenMetadata Agent - Chat UI con Streamlit
Interfaz conversacional para explorar el catálogo de datos.
"""

import os
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

# Cargar configuración
load_dotenv(Path(__file__).parent / ".env")

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# Importar tools del MCP server
from server import (
    search_catalog,
    list_tables,
    get_table_details,
    list_databases,
    list_glossary_terms,
    get_lineage
)

# Configuración
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
OPENMETADATA_URL = os.getenv("OPENMETADATA_URL", "http://localhost:8585")

# Info de herramientas para el LLM
TOOLS_INFO = """
Herramientas disponibles para explorar el catálogo de datos:
1. search_catalog(query) - Buscar assets por término (tablas, pipelines, etc.)
2. list_tables(limit) - Listar tablas disponibles con su esquema
3. get_table_details(table_name) - Ver columnas y detalles de una tabla específica
4. list_databases() - Ver todas las bases de datos registradas
5. get_lineage(asset_name) - Ver el linaje de datos (origen y destino)
6. list_glossary_terms() - Ver términos del glosario de negocio
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
- Para listar tablas: FUNCTION: list_tables, PARAMS: limit=15
- Para buscar: FUNCTION: search_catalog, PARAMS: query=término
- Para detalles: FUNCTION: get_table_details, PARAMS: table_name=nombre_tabla
- Para bases de datos: FUNCTION: list_databases, PARAMS: none
- Para linaje: FUNCTION: get_lineage, PARAMS: asset_name=nombre
- Para glosario: FUNCTION: list_glossary_terms, PARAMS: none
"""

    decision_response = llm.invoke([HumanMessage(content=decision_prompt)])
    decision = decision_response.content.strip()
    
    # Paso 2: Ejecutar la herramienta
    try:
        if "list_tables" in decision:
            limit = 15
            if "limit=" in decision:
                try:
                    limit = int(decision.split("limit=")[1].split()[0].strip(","))
                except:
                    pass
            result = list_tables(limit=limit)
            
        elif "search_catalog" in decision:
            search_term = query  # Default
            if "query=" in decision:
                search_term = decision.split("query=")[1].split("\n")[0].strip().strip(",")
            result = search_catalog(search_term, limit=10)
            
        elif "get_table_details" in decision:
            table_name = ""
            if "table_name=" in decision:
                table_name = decision.split("table_name=")[1].split("\n")[0].strip().strip(",")
            if not table_name:
                # Intentar extraer de la pregunta
                words = query.lower().replace("tabla", "").replace("table", "").split()
                table_name = words[-1] if words else ""
            result = get_table_details(table_name)
            
        elif "list_databases" in decision:
            result = list_databases()
            
        elif "get_lineage" in decision:
            asset_name = ""
            if "asset_name=" in decision:
                asset_name = decision.split("asset_name=")[1].split("\n")[0].strip().strip(",")
            if not asset_name:
                words = query.split()
                asset_name = words[-1] if words else ""
            result = get_lineage(asset_name)
            
        elif "list_glossary_terms" in decision:
            result = list_glossary_terms()
            
        else:
            result = "No pude determinar qué herramienta usar para esta pregunta."
            
    except Exception as e:
        result = f"Error ejecutando la consulta: {str(e)}"
    
    # Paso 3: Formatear respuesta natural
    format_prompt = f"""Eres un asistente de Data Governance amigable. Basándote en los datos obtenidos del catálogo, responde la pregunta del usuario de forma clara y útil.

Pregunta del usuario: "{query}"

Datos del catálogo:
{result}

Instrucciones:
- Responde en español
- Sé conciso pero informativo
- Si hay muchos resultados, resume los más relevantes
- Si no hay resultados, sugiere alternativas
- Usa formato markdown para mejor legibilidad
"""

    final_response = llm.invoke([HumanMessage(content=format_prompt)])
    return final_response.content

# ============== STREAMLIT UI ==============

st.set_page_config(
    page_title="OpenMetadata Agent",
    page_icon="🔍",
    layout="wide"
)

# Header
st.title("🔍 OpenMetadata Agent")
st.caption(f"Asistente conversacional para tu catálogo de datos | Conectado a: `{OPENMETADATA_URL}`")

# Sidebar con info
with st.sidebar:
    st.header("ℹ️ Acerca de")
    st.markdown("""
    Este agente te permite explorar el catálogo de datos 
    de OpenMetadata usando lenguaje natural.
    
    **Ejemplos de preguntas:**
    - ¿Cuántas tablas tenemos?
    - ¿Qué columnas tiene la tabla customers?
    - Busca tablas relacionadas con ventas
    - ¿De dónde vienen los datos de la tabla orders?
    - ¿Qué bases de datos tenemos?
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

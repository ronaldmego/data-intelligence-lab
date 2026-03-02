#!/usr/bin/env python3
"""
OpenMetadata Agent - Chat UI con Streamlit
Interfaz conversacional para explorar el catálogo de datos.
Usa function calling nativo de Gemini para selección automática de tools.
"""

import os
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

# Cargar configuración
load_dotenv(Path(__file__).parent / ".env")

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

# Importar tools del MCP server
from server import (
    search_catalog,
    list_tables,
    get_table_details,
    list_databases,
    list_glossary_terms,
    get_lineage,
    list_domains,
    update_table_description,
    update_column_description,
)

# Configuración
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
OPENMETADATA_URL = os.getenv("OPENMETADATA_URL", "http://localhost:8585")

# Registro de tools: lista y lookup por nombre
TOOLS = [search_catalog, list_tables, get_table_details, list_databases,
         list_glossary_terms, get_lineage, list_domains,
         update_table_description, update_column_description]
TOOLS_BY_NAME = {fn.__name__: fn for fn in TOOLS}

SYSTEM_PROMPT = (
    "Eres un asistente de Data Governance experto. "
    "Usa las herramientas disponibles para responder preguntas sobre el catálogo de datos de OpenMetadata. "
    "Responde siempre en español. Usa formato markdown para mejor legibilidad.\n\n"
    "ESTRATEGIA DE BÚSQUEDA:\n"
    "1. Si search_catalog no devuelve resultados, usa list_tables o list_databases para descubrir nombres correctos.\n"
    "2. Si el usuario escribe mal un nombre, busca coincidencias parciales en los listados.\n"
    "3. Puedes encadenar herramientas: search → list_tables → get_table_details.\n"
    "4. No te rindas en el primer intento. Siempre intenta al menos una estrategia alternativa antes de decir que no encontraste nada.\n\n"
    "HERRAMIENTAS DE ESCRITURA (update_table_description, update_column_description):\n"
    "1. Antes de ejecutar una herramienta de escritura, SIEMPRE confirma con el usuario mostrando exactamente qué se va a cambiar.\n"
    "2. Muestra: tabla/columna afectada y la nueva descripción propuesta. Pregunta '¿Confirmas el cambio?'.\n"
    "3. Solo ejecuta la herramienta de escritura después de recibir confirmación explícita del usuario.\n"
    "4. Después de una escritura exitosa, confirma qué se cambió."
)

MAX_TOOL_ITERATIONS = 10


def extract_text(content) -> str:
    """Extraer texto plano del content de Gemini, que puede ser str o lista de bloques."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts) if parts else str(content)
    return str(content) if content else ""


def init_llm():
    """Inicializar el modelo de Gemini con tools bindeados"""
    llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=0)
    return llm.bind_tools(TOOLS)


def agent_process(query: str, llm, chat_history: list = None) -> dict:
    """Procesar query usando function calling nativo de Gemini.

    El LLM decide qué tools usar, puede encadenar varias, y responde
    cuando tiene suficiente información.

    Retorna dict con: response, tool_trace (lista de calls ejecutados)
    """
    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    # Inyectar historial reciente (últimos 10 mensajes = 5 turnos)
    if chat_history:
        for msg in chat_history[-10:]:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

    messages.append(HumanMessage(content=query))

    tool_trace = []  # Para el debug expander

    for _ in range(MAX_TOOL_ITERATIONS):
        ai_message = llm.invoke(messages)
        messages.append(ai_message)

        # Si no hay tool calls, tenemos la respuesta final
        if not ai_message.tool_calls:
            return {
                "response": extract_text(ai_message.content),
                "tool_trace": tool_trace,
            }

        # Ejecutar cada tool call
        for tool_call in ai_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_fn = TOOLS_BY_NAME.get(tool_name)

            if tool_fn is None:
                result = f"Tool '{tool_name}' no encontrada"
            else:
                try:
                    result = tool_fn(**tool_args)
                except Exception as e:
                    result = f"Error ejecutando {tool_name}: {str(e)}"

            # Registrar para debug
            tool_trace.append({
                "tool": tool_name,
                "args": tool_args,
                "result": str(result),
            })

            # Devolver resultado al LLM
            messages.append(ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"],
                name=tool_name,
            ))

    # Fallback si se alcanzó el límite de iteraciones
    return {
        "response": extract_text(ai_message.content) or "Se alcanzó el límite de iteraciones del agente.",
        "tool_trace": tool_trace,
    }


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
    - ¿Qué dominios tiene el catálogo?

    **Escritura:**
    - Actualiza la descripción de la tabla customers a "Clientes activos del sistema"
    - Cambia la descripción de la columna email en customers a "Correo principal del cliente"
    """)

    st.divider()

    st.header("⚙️ Configuración")
    st.text(f"Modelo: {GEMINI_MODEL}")
    st.text(f"OpenMetadata: {OPENMETADATA_URL}")
    tools_list = ", ".join(fn.__name__ for fn in TOOLS)
    st.text(f"Tools ({len(TOOLS)}): {tools_list}")

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


def render_debug(tool_trace: list):
    """Renderizar debug expander con el trace de tools usadas"""
    if not tool_trace:
        return
    summary = " → ".join(f"`{t['tool']}`" for t in tool_trace)
    with st.expander(f"🔧 Tools: {summary}", expanded=False):
        for i, t in enumerate(tool_trace):
            st.markdown(f"**Paso {i + 1}: `{t['tool']}`**")
            st.code(f"args: {t['args']}", language="json")
            st.code(t["result"], language="text")
            if i < len(tool_trace) - 1:
                st.divider()


# Mostrar historial de mensajes
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "tool_trace" in message:
            render_debug(message["tool_trace"])

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
                result = agent_process(prompt, st.session_state.llm, st.session_state.messages)
                st.markdown(result["response"])
                render_debug(result["tool_trace"])

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": result["response"],
                    "tool_trace": result["tool_trace"],
                })
            except Exception as e:
                error_msg = f"❌ Error: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

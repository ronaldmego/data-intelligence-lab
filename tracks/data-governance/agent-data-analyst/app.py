#!/usr/bin/env python3
"""
DataGov Analyst - Super Analista de Datos con IA
UI conversacional con arquitectura MCP plug & play.

Cada fuente de datos es un MCP independiente.
Agregar un nuevo MCP = agregar una línea en agent.py
"""

import os
import asyncio
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv
from viz import parse_viz_request, render_viz

# Cargar configuración
load_dotenv(Path(__file__).parent / ".env")

from agent import create_agent, LLM_PROVIDER

# Configuración
OPENMETADATA_URL = os.getenv("OPENMETADATA_URL", "http://localhost:8585")

# ============== STREAMLIT UI ==============

st.set_page_config(
    page_title="DataGov Analyst",
    page_icon="📊",
    layout="wide"
)

# Header
st.title("📊 DataGov SQL AI Analyst")
st.caption("Open Source · Self-Hosted · Powered by OpenMetadata · LangChain · MCP")

# Sidebar
with st.sidebar:
    st.header("ℹ️ Acerca de")
    st.markdown("""
    **DataGov Analyst** — Super Analista de Datos con IA.
    
    Arquitectura MCP (Model Context Protocol):
    cada fuente de datos es un plugin independiente.
    
    **Ejemplos de preguntas:**
    - ¿Qué tablas tenemos?
    - Dame el perfil de la tabla customers
    - ¿Qué schemas hay disponibles?
    - Estadísticas de la columna city en customers
    - ¿De dónde vienen los datos de orders?
    - ¿Cuántos clientes activos hay?
    """)
    
    st.divider()
    
    st.header("🔌 MCPs Conectados")
    if "agent" in st.session_state and st.session_state.agent:
        for mcp_name in st.session_state.agent.mcp_servers:
            tools_count = sum(1 for t in st.session_state.agent.tools_registry.values() 
                            if t["mcp_name"] == mcp_name)
            st.success(f"✅ {mcp_name} ({tools_count} tools)")
    
    st.divider()
    
    st.header("⚙️ Configuración")
    if "agent" in st.session_state:
        provider_label = "🟢 Gemini (enterprise)" if LLM_PROVIDER == "gemini" else "🔵 OpenRouter (dev)"
        st.text(f"Provider: {provider_label}")
        st.text(f"Modelo: {st.session_state.agent.model_name}")
    st.text(f"OpenMetadata: {OPENMETADATA_URL}")
    
    st.divider()
    
    if st.button("🗑️ Limpiar chat"):
        st.session_state.messages = []
        st.rerun()

# Inicializar agente
if "agent" not in st.session_state:
    try:
        agent = create_agent()
        # Discover tools (async)
        asyncio.run(agent.discover_tools())
        st.session_state.agent = agent
    except Exception as e:
        st.error(f"Error inicializando agente: {e}")
        st.stop()

# Inicializar historial
if "messages" not in st.session_state:
    st.session_state.messages = []

# Mostrar historial
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input del usuario
if prompt := st.chat_input("Pregunta sobre tus datos..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("Analizando datos..."):
            try:
                response = asyncio.run(st.session_state.agent.process(prompt))

                # Detectar y renderizar bloque viz si existe
                viz_params = parse_viz_request(response)
                if viz_params:
                    # Mostrar texto sin el bloque viz
                    import re
                    clean_response = re.sub(r"```viz.*?```", "", response, flags=re.DOTALL).strip()
                    st.markdown(clean_response)
                    fig = render_viz(viz_params)
                    if fig:
                        st.pyplot(fig)
                        import matplotlib.pyplot as plt
                        plt.close(fig)
                else:
                    st.markdown(response)

                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                error_msg = f"❌ Error: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

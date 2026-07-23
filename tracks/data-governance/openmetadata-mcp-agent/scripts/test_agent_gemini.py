#!/usr/bin/env python3
"""
Test del agente conversacional con Gemini para OpenMetadata.
Versión simplificada usando LangChain.

Requiere: .env con GOOGLE_API_KEY configurada
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Cargar API key desde .env (NUNCA hardcodear!)
load_dotenv(Path(__file__).parent.parent / ".env")

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from server import get_lineage, get_table_details, list_databases, list_tables, search_catalog

# Mapeo de intenciones a funciones
TOOLS_INFO = """
Herramientas disponibles:
1. search_catalog(query) - Buscar assets por término
2. list_tables(limit) - Listar tablas disponibles
3. get_table_details(table_name) - Ver columnas de una tabla
4. list_databases() - Ver bases de datos
5. get_lineage(asset_name) - Ver linaje de datos
"""

def agent_decide_and_execute(query: str, llm) -> str:
    """El LLM decide qué herramienta usar y la ejecutamos."""

    # Paso 1: El LLM decide qué hacer
    decision_prompt = f"""Eres un asistente de Data Governance. Analiza esta pregunta y decide qué herramienta usar.

{TOOLS_INFO}

Pregunta del usuario: "{query}"

Responde SOLO con el nombre de la función y parámetros en formato:
FUNCTION: nombre_funcion
PARAMS: parametro1=valor1

Si necesitas listar tablas, usa: FUNCTION: list_tables, PARAMS: limit=10
Si necesitas buscar algo, usa: FUNCTION: search_catalog, PARAMS: query=término
Si necesitas detalles de tabla, usa: FUNCTION: get_table_details, PARAMS: table_name=nombre
"""

    response = llm.invoke([HumanMessage(content=decision_prompt)])
    decision = response.content.strip()

    print(f"   🧠 Decisión del LLM: {decision}")

    # Paso 2: Parsear y ejecutar
    try:
        if "list_tables" in decision:
            result = list_tables(limit=10)
        elif "search_catalog" in decision:
            # Extraer query
            if "query=" in decision:
                search_term = decision.split("query=")[1].split("\n")[0].strip()
            else:
                search_term = query  # Usar la pregunta original
            result = search_catalog(search_term, limit=5)
        elif "get_table_details" in decision:
            # Extraer table_name
            if "table_name=" in decision:
                table = decision.split("table_name=")[1].split("\n")[0].strip()
            else:
                # Intentar extraer de la pregunta
                table = query.split("tabla")[-1].strip().split()[0] if "tabla" in query else "assessment_results"
            result = get_table_details(table)
        elif "list_databases" in decision:
            result = list_databases()
        elif "get_lineage" in decision:
            if "asset_name=" in decision:
                asset = decision.split("asset_name=")[1].split("\n")[0].strip()
            else:
                asset = query.split()[-1]
            result = get_lineage(asset)
        else:
            result = "No pude determinar qué herramienta usar."
    except Exception as e:
        result = f"Error ejecutando herramienta: {e}"

    # Paso 3: El LLM formatea la respuesta
    format_prompt = f"""Eres un asistente de Data Governance amigable. Basándote en los datos obtenidos del catálogo, responde la pregunta del usuario de forma clara y útil.

Pregunta: "{query}"

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

def main():
    print("\n" + "="*60)
    print("🤖 Agente OpenMetadata con Gemini")
    print("="*60)

    # Verificar API key
    if not os.getenv("GOOGLE_API_KEY"):
        print("❌ Error: GOOGLE_API_KEY no está configurada en .env")
        return

    # Inicializar LLM
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
    llm = ChatGoogleGenerativeAI(model=model, temperature=0)

    # Test queries
    queries = [
        "¿Cuántas tablas tenemos?",
        "¿Qué columnas tiene la tabla assessment_results?",
        "Busca tablas de leads"
    ]

    for query in queries:
        print(f"\n{'='*60}")
        print(f"🗣️  Usuario: {query}")
        print("-"*60)

        try:
            result = agent_decide_and_execute(query, llm)
            print(f"\n🤖 Respuesta:\n{result}")
        except Exception as e:
            print(f"❌ Error: {e}")

    print("\n" + "="*60)
    print("✅ Test completado!")
    print("="*60)

if __name__ == "__main__":
    main()

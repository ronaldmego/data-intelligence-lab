#!/usr/bin/env python3
"""
Khipu Analytics - Agent Core
Cerebro del agente: conecta a MCPs como plugins y orquesta con un LLM.

Arquitectura plug & play:
- Cada MCP es un "brazo" independiente (OpenMetadata, SQL, futuro: Snowflake, BigQuery)
- El agente descubre tools automáticamente de cada MCP conectado
- Agregar un nuevo MCP = agregar una entrada en agent.py
- LLM configurable: Gemini (enterprise) o cualquier modelo via OpenRouter (dev/testing)
"""

import os
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from fastmcp import Client
from langchain_core.messages import HumanMessage

load_dotenv(Path(__file__).parent / ".env")

# LLM Configuration
# LLM_PROVIDER: "gemini" (enterprise, paid) or "openrouter" (dev/testing, free models available)
# Set in .env or defaults to openrouter for cost savings during development
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-r1-0528:free")
OPENROUTER_API_KEY = os.getenv("OPEN_ROUTER_API_KEY", "")


def create_llm():
    """Crear LLM según el provider configurado.
    
    - gemini: Google Gemini via API key (enterprise/production)
    - openrouter: Cualquier modelo via OpenRouter (dev/testing, modelos gratis disponibles)
    """
    if LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=0), GEMINI_MODEL
    else:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=OPENROUTER_MODEL,
            openai_api_key=OPENROUTER_API_KEY,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0,
        ), OPENROUTER_MODEL


class KhipuAgent:
    """Agente que conecta a múltiples MCPs y orquesta con un LLM."""

    def __init__(self):
        self.llm, self.model_name = create_llm()
        self.mcp_servers = {}  # name -> FastMCP server object
        self.tools_registry = {}  # tool_name -> {mcp_name, description, params}
        self.tools_info = ""  # Text description for the LLM

    def register_mcp(self, name: str, server):
        """Registrar un MCP server como plugin.
        
        Args:
            name: Nombre del MCP (ej: 'openmetadata', 'sql', 'snowflake')
            server: FastMCP server object
        """
        self.mcp_servers[name] = server

    async def discover_tools(self):
        """Descubrir tools de todos los MCPs registrados."""
        self.tools_registry = {}
        sections = []

        for mcp_name, server in self.mcp_servers.items():
            async with Client(server) as client:
                tools = await client.list_tools()
                tool_lines = []
                for tool in tools:
                    self.tools_registry[tool.name] = {
                        "mcp_name": mcp_name,
                        "description": tool.description or "",
                        "params": tool.inputSchema if hasattr(tool, 'inputSchema') else {}
                    }
                    # Extract param names from schema
                    params = ""
                    if hasattr(tool, 'inputSchema') and tool.inputSchema:
                        props = tool.inputSchema.get("properties", {})
                        if props:
                            param_list = []
                            for p_name, p_info in props.items():
                                p_type = p_info.get("type", "string")
                                param_list.append(f"{p_name}({p_type})")
                            params = f"({', '.join(param_list)})"
                    
                    tool_lines.append(f"  - {tool.name}{params}: {(tool.description or '')[:80]}")
                
                sections.append(f"🔌 MCP: {mcp_name} ({len(tools)} tools)\n" + "\n".join(tool_lines))

        self.tools_info = "\n\n".join(sections)
        return self.tools_registry

    async def call_tool(self, tool_name: str, params: dict) -> str:
        """Ejecutar un tool de cualquier MCP registrado."""
        if tool_name not in self.tools_registry:
            return f"❌ Tool '{tool_name}' no encontrada"

        mcp_name = self.tools_registry[tool_name]["mcp_name"]
        server = self.mcp_servers[mcp_name]

        async with Client(server) as client:
            result = await client.call_tool(tool_name, params)
            return result.data if hasattr(result, 'data') and result.data else str(result)

    async def process(self, query: str) -> str:
        """Procesar pregunta del usuario con razonamiento multi-step."""
        return await self.process_multi_step(query)

    async def process_multi_step(self, query: str, max_steps: int = 5) -> str:
        """Procesar pregunta del usuario con múltiples tool calls en secuencia.
        
        Flujo: pregunta → step1 (tool call) → resultado1 → step2 (tool call con contexto) → ... → DONE → respuesta final
        
        Args:
            query: Pregunta del usuario
            max_steps: Máximo número de tool calls permitidos (safety limit)
        """
        
        accumulated_context = []
        step = 1
        
        while step <= max_steps:
            # Crear contexto acumulativo
            context_summary = ""
            if accumulated_context:
                context_summary = "\n\n".join([
                    f"PASO {i+1} PREVIO:\n- Tool usado: {ctx['tool_name']}\n- Parámetros: {ctx['params']}\n- Resultado: {ctx['result'][:500]}..."
                    for i, ctx in enumerate(accumulated_context)
                ])
            
            # Decidir próximo paso
            decision_prompt = f"""Eres Khipu Analytics, un Super Analista de Datos con IA.
Tienes acceso a múltiples fuentes de datos via MCP (Model Context Protocol).

Tools disponibles:
{self.tools_info}

Pregunta original del usuario: "{query}"

CONTEXTO PREVIO (pasos ya ejecutados):
{context_summary if context_summary else "NINGUNO - Este es el primer paso"}

ESTRATEGIA MULTI-STEP (best practice):
1. SIEMPRE empieza por OpenMetadata cuando el usuario pregunta sobre una tabla:
   - OpenMetadata da la visión gobernada (descripción, tags, owner, linaje, glosario)
   - Es tu fuente de verdad de contexto, independiente del motor de base de datos
2. Usa SQL para datos REALES: estadísticas, conteos, distribuciones, valores concretos
3. Lo ideal es combinar: primero contexto (OpenMetadata), luego datos reales (SQL)
4. Para análisis complejos, múltiples pasos:
   - "Describe tabla customers" → OpenMetadata (contexto) + SQL (estadísticas reales)
   - "Relaciones entre tablas" → OpenMetadata lineage + SQL para validar FKs
   - "Análisis por grupo" → OpenMetadata (entender columnas) + SQL (GROUP BY)

DECISIÓN - Responde con UNA de estas opciones:

Opción A - Hacer otro tool call:
TOOL: nombre_del_tool
PARAMS: param1=valor1, param2=valor2

Opción B - Tengo suficiente información para responder al usuario:
DONE

⚠️ IMPORTANTE: Sé exhaustivo. Si el usuario pregunta por tablas, no basta con listar databases — también lista schemas/tablas.
Si obtuviste metadata de una tabla, complementa con estadísticas SQL. Busca dar respuestas completas.

Paso actual: {step}/{max_steps}

Ejemplos de decisiones:
- Si no tengo contexto de la tabla → TOOL: get_table_details (OpenMetadata primero)
- Si tengo contexto pero necesito estadísticas → TOOL: get_table_profile (SQL después)
- Si tengo todo lo necesario → DONE
- Si usuario pregunta por relaciones → TOOL: get_lineage luego SQL para validar
"""

            decision_response = self.llm.invoke([HumanMessage(content=decision_prompt)])
            decision = decision_response.content.strip()
            
            # Verificar si el LLM decide terminar
            if "DONE" in decision.upper():
                break
                
            # Parsear y ejecutar tool call
            try:
                tool_name = ""
                params = {}

                for line in decision.split("\n"):
                    line = line.strip()
                    if line.startswith("TOOL:"):
                        raw_tool = line.split("TOOL:")[1].strip().split(",")[0].strip()
                        # Strip MCP prefix if LLM adds it (e.g. "openmetadata.list_tables" → "list_tables")
                        tool_name = raw_tool.split(".")[-1] if "." in raw_tool else raw_tool
                    elif line.startswith("PARAMS:"):
                        params_str = line.split("PARAMS:")[1].strip()
                        if params_str.lower() != "none":
                            for pair in params_str.split(","):
                                pair = pair.strip()
                                if "=" in pair:
                                    key, val = pair.split("=", 1)
                                    key = key.strip()
                                    val = val.strip()
                                    # Try to convert numeric
                                    try:
                                        val = int(val)
                                    except ValueError:
                                        pass
                                    params[key] = val

                if not tool_name:
                    # Si no se pudo parsear, terminar con lo que tenemos
                    break
                    
                # Ejecutar tool
                result = await self.call_tool(tool_name, params)
                
                # Guardar en contexto acumulativo
                accumulated_context.append({
                    "step": step,
                    "tool_name": tool_name,
                    "params": params,
                    "result": result
                })
                
                step += 1

            except Exception as e:
                # En caso de error, guardar el error y continuar
                accumulated_context.append({
                    "step": step,
                    "tool_name": tool_name,
                    "params": params,
                    "result": f"Error: {str(e)}"
                })
                break
        
        # Generar respuesta final basada en todo el contexto acumulado
        all_results = "\n\n".join([
            f"PASO {ctx['step']}: {ctx['tool_name']}({ctx['params']})\nResultado:\n{ctx['result']}"
            for ctx in accumulated_context
        ])
        
        format_prompt = f"""Eres Khipu Analytics, un Super Analista de Datos. Has ejecutado {len(accumulated_context)} pasos para responder la pregunta del usuario.

Pregunta original: "{query}"

Datos obtenidos en {len(accumulated_context)} pasos:
{all_results}

Instrucciones para la respuesta final:
- Responde en español
- Sintetiza toda la información de los múltiples pasos ejecutados
- Sé conciso pero informativo
- Si hay datos numéricos, resalta insights (Top 3, %, anomalías)
- Interpreta los datos: no solo números, sino qué significan
- Usa formato markdown
- Si los datos sugieren un siguiente paso de análisis, proponlo
- Menciona brevemente qué pasos seguiste para obtener la información (transparencia del proceso)
"""

        final_response = self.llm.invoke([HumanMessage(content=format_prompt)])
        return final_response.content


def create_agent() -> KhipuAgent:
    """Crear agente con los MCPs configurados."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))

    agent = KhipuAgent()

    # Registrar MCPs disponibles
    from server import mcp as openmetadata_mcp
    agent.register_mcp("openmetadata", openmetadata_mcp)

    from sql_server import sql_mcp
    agent.register_mcp("sql", sql_mcp)

    # Futuro: agregar más MCPs aquí
    # from snowflake_server import snowflake_mcp
    # agent.register_mcp("snowflake", snowflake_mcp)
    #
    # from bigquery_server import bq_mcp
    # agent.register_mcp("bigquery", bq_mcp)

    return agent


# Para testing directo
if __name__ == "__main__":
    async def main():
        agent = create_agent()
        await agent.discover_tools()
        print(f"Tools registradas: {len(agent.tools_registry)}")
        print(agent.tools_info)
        print("\n--- Test query ---\n")
        result = await agent.process("Dame el perfil de la tabla customers en telco_demo")
        print(result)

    asyncio.run(main())

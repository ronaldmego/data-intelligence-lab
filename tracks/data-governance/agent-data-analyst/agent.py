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
import re
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from fastmcp import Client
from langchain_core.messages import HumanMessage
from classifier import classify_column, classifications_to_prompt

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

    def _extract_classifications(self, accumulated_context: list) -> str:
        """
        Extraer clasificaciones de variables del resultado de get_table_profile.
        Parsea el output de texto del MCP SQL para clasificar las columnas.
        """
        profile_result = None
        total_rows = 0

        for ctx in accumulated_context:
            if ctx["tool_name"] == "get_table_profile":
                profile_result = ctx["result"]
                # Extraer row count del resultado (formato: "Filas: X,XXX")
                match = re.search(r"Filas:\s*([\d,]+)", profile_result)
                if match:
                    total_rows = int(match.group(1).replace(",", ""))
                break

        if not profile_result or total_rows == 0:
            return ""

        # Parsear líneas de columnas (formato: "  col_name (type): N únicos, X% nulls")
        classifications = []
        pattern = re.compile(
            r"^\s{2}(\S+)\s+\(([^)]+)\):\s*(\d[\d,]*)\s+únicos,\s*([\d.]+)%\s+nulls",
            re.MULTILINE,
        )
        for match in pattern.finditer(profile_result):
            col_name = match.group(1)
            sql_type = match.group(2).strip()
            cardinality = int(match.group(3).replace(",", ""))
            null_pct = float(match.group(4))

            c = classify_column(
                column_name=col_name,
                sql_type=sql_type,
                cardinality=cardinality,
                total_rows=total_rows,
                null_pct=null_pct,
            )
            classifications.append(c)

        if not classifications:
            return ""

        return classifications_to_prompt(classifications)

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

1. PERFIL DE TABLA (keywords: perfil, profile, describe, detalles, columnas, estructura):
   - Paso 1: get_table_details (OpenMetadata) → descripción, owner, tags, columnas con sus tipos
   - Paso 2: get_table_profile (SQL) → row count, nulls%, cardinalidad, min/max/avg por columna
   - SOLO después de ambos pasos → DONE

2. ESTADÍSTICAS DE COLUMNA (keywords: estadísticas, distribución, stats de columna X):
   - Paso 1: get_table_details (OpenMetadata) → contexto de la tabla
   - Paso 2: get_column_stats (SQL) → estadísticas detalladas de la columna específica
   - SOLO después de ambos pasos → DONE

3. DESCUBRIMIENTO (keywords: qué tablas, listar, schemas, qué datos):
   - Paso 1: list_databases o list_tables (OpenMetadata) → inventario
   - Si el usuario pregunta por tablas y solo tienes databases → list_tables también
   - DONE cuando tengas el inventario completo

4. CALIDAD DE DATOS (keywords: calidad, quality, nulls, duplicados, problemas, reporte de calidad):
   - Paso 1: get_table_details (OpenMetadata) → descripción, owner, tags
   - Paso 2: get_table_profile (SQL) → nulls%, cardinalidad, row count por columna
   - SOLO después de ambos pasos → DONE

5. LINAJE (keywords: de dónde vienen, linaje, upstream, downstream):
   - Paso 1: get_lineage (OpenMetadata) → grafo de dependencias
   - DONE con el linaje

6. GLOSARIO / NEGOCIO (keywords: qué significa, definición, glosario):
   - Paso 1: list_glossary_terms o search_catalog
   - DONE con las definiciones

DECISIÓN - Responde con UNA de estas opciones:

Opción A - Hacer otro tool call:
TOOL: nombre_del_tool
PARAMS: param1=valor1, param2=valor2

Opción B - Tengo suficiente información para responder al usuario:
DONE

⚠️ REGLAS:
- Para PERFIL o DESCRIBE: NUNCA hagas DONE con solo 1 paso — necesitas OpenMetadata Y SQL
- Para get_table_profile y get_column_stats necesitas: schema_name y table_name exactos
- Si OpenMetadata te dio el FQN (ej: service.db.schema.table), extrae schema y table de ahí
- Si el usuario no especificó schema, usa el que encontraste en OpenMetadata

Paso actual: {step}/{max_steps}
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

        # Extraer clasificación de variables si hay un get_table_profile en el contexto
        classification_text = self._extract_classifications(accumulated_context)

        # Detectar tipo de pregunta para guiar el formato de respuesta
        query_lower = query.lower()
        is_profile = any(w in query_lower for w in ["perfil", "profile", "describe", "detalles", "estructura", "columnas"])
        is_stats = any(w in query_lower for w in ["estadísticas", "estadisticas", "stats", "distribución", "distribucion"])
        is_viz = any(w in query_lower for w in ["gráfico", "grafico", "chart", "histograma", "barras", "ranking", "distribución visual", "visualiza", "muestra gráfico"])
        is_quality = any(w in query_lower for w in ["calidad", "quality", "nulls", "nulos", "duplicados", "problemas", "reporte de calidad", "data quality"])
        is_analysis_detect = any(w in query_lower for w in ["qué análisis", "que analisis", "cómo analizo", "como analizo", "qué puedo hacer", "analizar", "explorar"])

        if is_profile:
            classification_section = f"\n{classification_text}\n" if classification_text else ""
            format_instructions = f"""
FORMATO PARA PERFIL DE TABLA — sigue esta estructura exacta:

## 📊 Perfil: [nombre de la tabla]

### Contexto (OpenMetadata)
- **Descripción:** ...
- **Owner:** ...
- **Tags:** ...
- **FQN:** ...

### Estructura y Estadísticas

| Columna | Tipo estadístico | Tipo SQL | Nulos % | Valores únicos | Observación |
|---------|-----------------|----------|---------|----------------|-------------|
| col1    | numérica_continua | integer | 0%   | 1,234          | min/max/avg |
| col2    | categórica       | text    | 5.2%  | 45             | top valores |
...
{classification_section}
> **Resumen:** X filas · Y columnas · [observación clave]

### 💡 Insights automáticos
Aplica estas reglas sobre los datos obtenidos — solo menciona los que apliquen:
- **Columnas con nulls altos** (>10%): mencionar como alerta 🔴
- **Columna constante** (1 único valor): alertar como posible problema de calidad
- **Columna dominante** (1 valor >50%): "El X% de los registros tiene valor Y"
- **Regla de Pareto**: si el 80% está en pocas categorías, mencionarlo
- **Identificadores** (cardinalidad ~100%): no analizar, solo confirmar unicidad

### Siguiente paso sugerido
Basándote en los tipos de variables y problemas encontrados, propón UN análisis concreto.
- Si hay columnas con nulls altos o constantes → sugerir reporte de calidad completo
- Si hay temporales + numéricas → sugerir análisis de tendencia
- Si hay categóricas + numéricas → sugerir distribución por grupo
- Si hay 2+ numéricas → sugerir análisis de correlación
"""
        elif is_stats or is_viz:
            format_instructions = """
FORMATO PARA ESTADÍSTICAS Y VISUALIZACIÓN:
- Muestra las métricas en formato estructurado (lista o tabla markdown)

### 💡 Insights automáticos (incluir siempre que aplique)
Revisa los datos y menciona los insights que encuentres:

**Para variables categóricas:**
- Top 3 valores con conteo y % del total
- Regla de Pareto: si el 80% está en pocas categorías → "El 80% de los registros se concentra en X categorías"
- Valor dominante: si un valor supera el 50% → "Y representa el Z% de todos los registros"
- Diversidad: si hay muchas categorías con distribución uniforme, mencionarlo

**Para variables numéricas:**
- Rango (min → max) e interpretación
- Sesgo: si media >> mediana → distribución sesgada a la derecha (outliers altos)
- Outliers: si P75 + 1.5×IQR < max, hay outliers potenciales → mencionar
- Percentil 90: "El 90% de los valores está por debajo de X"

**Para cualquier columna:**
- Nulls altos (>10%): alerta 🔴
- Columna constante (1 único): alerta de calidad

IMPORTANTE — Si tienes datos suficientes para un gráfico, incluye al final un bloque viz:
```viz
type: bar_chart | histogram | line_chart | boxplot
col_name: nombre_columna
categories: val1,val2,val3        (solo para bar_chart)
values: 100,200,300               (frecuencias para bar_chart, o datos para histogram)
x_values: ene,feb,mar             (solo para line_chart)
y_values: 10,20,30                (solo para line_chart)
title: Título del gráfico en español
```

Reglas para el bloque viz:
- bar_chart: usa cuando hay categorías con frecuencias (categórica, numérica_discreta, booleana)
- histogram: usa cuando hay lista de valores numéricos continuos
- line_chart: usa cuando hay serie temporal (fecha + métrica)
- boxplot: usa cuando hay distribución numérica sin categorías claras
- SOLO incluye el bloque si tienes los datos reales — nunca inventes valores
- Los valores deben venir de los resultados SQL obtenidos en los pasos anteriores
"""
        elif is_quality:
            format_instructions = """
FORMATO PARA REPORTE DE CALIDAD — sigue esta estructura exacta:

## 🔍 Reporte de Calidad: [nombre tabla]

| Columna | Tipo | Nulls % | Únicos | Estado | Observación |
|---------|------|---------|--------|--------|-------------|
| col1    | int  | 0%      | 10,432 | 🟢     | ID único    |
| col2    | text | 12.3%   | 45     | 🔴     | Nulls altos |
| col3    | text | 0%      | 1      | 🔴     | Constante   |

**Semáforo:**
- 🟢 Verde: nulls < 1%, sin anomalías
- 🟡 Amarillo: nulls 1–10%, o cardinalidad sospechosa
- 🔴 Rojo: nulls > 10%, columna constante, o 100% nula

### 📋 Problemas detectados
Lista solo los problemas reales encontrados:
- 🔴 `col_name`: descripción del problema
- 🟡 `col_name`: descripción del problema

### 💡 Recomendaciones
Una recomendación accionable por cada columna en 🔴 o 🟡.

### ✅ Resumen de salud
> X columnas buenas · Y columnas con advertencia · Z columnas con problemas
"""
        elif is_analysis_detect:
            format_instructions = f"""
FORMATO PARA DETECCIÓN DE TIPO DE ANÁLISIS:

Después de describir brevemente los datos obtenidos, propón los análisis detectables:

### 🔭 Análisis posibles detectados

Revisa las columnas disponibles y detecta los patrones:

| Patrón detectado | Columnas | Tipo de análisis | Gráfico sugerido |
|-----------------|----------|-----------------|-----------------|
| fecha + métrica | created_at + revenue | Tendencia temporal | Line chart |
| categórica + numérica | segment + revenue | Distribución por grupo | Boxplot |
| 2 numéricas | age + revenue | Correlación | Scatter plot |
| categórica sola | status | Composición | Bar chart |

Para cada patrón encontrado en los datos REALES (no inventes columnas):
1. Describe qué patrón detectaste
2. Propón el análisis concreto con una pregunta de ejemplo
3. Indica el gráfico apropiado

⚠️ IMPORTANTE: El agente PROPONE — no ejecuta. Termina con:
> "¿Quieres que ejecute alguno de estos análisis? Dime cuál y lo hago paso a paso."
{f"Clasificación de variables disponible: {classification_text}" if classification_text else ""}
"""
        else:
            format_instructions = """
FORMATO GENERAL:
- Responde de forma estructurada con markdown
- Si hay listas de tablas/schemas, usa formato de lista o tabla
- Resalta los datos más relevantes
- Sé conciso pero completo
"""

        format_prompt = f"""Eres Khipu Analytics, un Super Analista de Datos. Has ejecutado {len(accumulated_context)} pasos para responder la pregunta del usuario.

Pregunta original: "{query}"

Datos obtenidos en {len(accumulated_context)} pasos:
{all_results}

INSTRUCCIONES GLOBALES:
- Responde siempre en español
- Interpreta los datos: no solo números, sino qué significan para el negocio
- Usa el tipo estadístico de cada columna para dar contexto (numérica_continua → distribución; categórica → concentración)
- Siempre que tengas frecuencias o conteos, calcula el % sobre el total y menciona si hay concentración
- Si hay anomalías (>10% nulls, columna constante, outliers evidentes), menciónalas con 🔴
- No inventes datos — si no tienes la información, dilo y propón obtenerla
{format_instructions}
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

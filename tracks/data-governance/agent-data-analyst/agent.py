#!/usr/bin/env python3
"""
DataGov Analyst - Agente de gobierno de datos
Cerebro del agente: conecta a MCPs como plugins y orquesta con un LLM.

Arquitectura plug & play:
- Cada MCP es un "brazo" independiente (OpenMetadata, SQL, futuro: Snowflake, BigQuery)
- El agente descubre tools automáticamente de cada MCP conectado
- Agregar un nuevo MCP = agregar una entrada en agent.py
- LLM configurable: Gemini (enterprise) o cualquier modelo via OpenRouter (dev/testing)
"""

import asyncio
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import Client
from langchain_core.messages import HumanMessage

from classifier import classifications_to_prompt, classify_column

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


class DataGovAgent:
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

    @staticmethod
    def _format_history(chat_history: list | None, max_turns: int = 10, max_chars: int = 1000) -> str:
        """Formatear los últimos mensajes de la conversación como bloque de texto.

        Mantiene contexto entre turnos sin explotar el prompt: trunca cada mensaje
        a max_chars y conserva sólo los últimos max_turns mensajes.
        """
        if not chat_history:
            return ""

        recent = chat_history[-max_turns:]
        lines = []
        for msg in recent:
            role = msg.get("role", "")
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            if len(content) > max_chars:
                content = content[:max_chars] + "…"
            label = "Usuario" if role == "user" else "Analista"
            lines.append(f"{label}: {content}")

        return "\n".join(lines)

    async def process(self, query: str, chat_history: list | None = None) -> str:
        """Procesar pregunta del usuario con razonamiento multi-step."""
        return await self.process_multi_step(query, chat_history=chat_history)

    async def process_multi_step(
        self, query: str, max_steps: int = 5, chat_history: list | None = None
    ) -> str:
        """Procesar pregunta del usuario con múltiples tool calls en secuencia.

        Flujo: pregunta → step1 (tool call) → resultado1 → step2 (tool call con contexto) → ... → DONE → respuesta final

        Args:
            query: Pregunta del usuario
            max_steps: Máximo número de tool calls permitidos (safety limit)
            chat_history: Lista opcional de mensajes previos [{role, content}, ...]
                para mantener contexto entre turnos. Se inyecta como texto en los prompts.
        """
        history_text = self._format_history(chat_history)
        history_block = (
            f"HISTORIAL DE CONVERSACIÓN PREVIA (para mantener contexto entre turnos):\n{history_text}\n\n"
            if history_text
            else ""
        )

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
            decision_prompt = f"""Eres DataGov Analyst, un agente de gobierno de datos.
Tienes acceso a múltiples fuentes de datos via MCP (Model Context Protocol).

Tools disponibles:
{self.tools_info}

{history_block}Pregunta actual del usuario: "{query}"
Si la pregunta hace referencia a algo mencionado antes (p. ej. "esa tabla", "ahora analízala"),
úsalo del HISTORIAL DE CONVERSACIÓN PREVIA para resolverlo.

CONTEXTO PREVIO (pasos ya ejecutados):
{context_summary if context_summary else "NINGUNO - Este es el primer paso"}

CONTEXTO DEL DEMO TELCO (aplica cuando la pregunta sea sobre el catálogo `telco_demo` / `Supabase-TelcoDemo`):

Empresa simulada: MVNO en Panamá, 100 suscriptores, 16 empleados, 6 planes ($5-$50/mes
prepago/postpago/empresa), 6 meses de operación (Nov 2025 - Abr 2026 + Mayo parcial). Revenue
~$22-25K/mes. **Estructuralmente no rentable a esta escala**: gross margin sano (~50%) pero
OpEx fijo (sobre todo nómina ~$8-10K/mes) consume casi toda la utilidad bruta. Net margin
negativo de Diciembre 2025 en adelante.

P&L mensual — receta canónica (la `Classification PL` en OM mapea cada línea a su tabla):
  Revenue Prepago   = SUM(recharges.amount)  filtrar amount > 0 AND amount < 1000
  Revenue Postpago  = SUM(payments.amount)   filtrar status='completed' AND 0 < amount < 10000
  COGS              = interconnect_costs_daily.total_cost + network_costs_monthly.total_cost
  OpEx              = marketing_spend.spend + payroll_monthly.total_cost
                      + 8% × Revenue (G&A modelado)
                      + chargebacks.amount (del mes, filtrar amount > 0 AND amount < 10000)
                      + 5% del bucket 61-90+ días de accounts_receivable
                        AT snapshot_date = MAX(snapshot_date) AND total_due > 0 AND total_due < 10000
                        (Bad Debt provision)
  EBITDA            = Revenue − COGS − OpEx
  Net Income        = EBITDA − 12% × Revenue (Depreciación modelada)
                            − 1.5% × Revenue (Intereses modelado)
                            − 25% × max(pre-tax, 0) (Tax Panamá)

⚠️ La data tiene outliers DQ intencionales ($99,999 en ~1% de filas en recharges/payments/invoices/accounts_receivable
   Y TAMBIÉN en chargebacks). SIEMPRE filtrar con los rangos arriba o los números se inflan absurdamente — sin el filtro
   de chargebacks el opex_bad_debt salta a $107K-$321K en algunos meses (vs cifras reales $283-$777).

⚠️ TABLA SNAPSHOT (accounts_receivable): es una foto diaria del estado de cobranzas. Una fila
   por cliente por día. Para cualquier pregunta sobre "estado actual de AR", "cuánto está vencido",
   "morosidad", "bad debt", FILTRAR siempre al snapshot más reciente:
     WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM telco_demo.accounts_receivable)
       AND total_due > 0 AND total_due < 10000
   Si NO filtrás, agregás todos los snapshots históricos (4,400 filas) y double-counteás al
   mismo cliente N veces — los montos se inflan ~50x. Esto vale para cualquier tabla con
   columnas tipo `snapshot_date`, `as_of_date`, `effective_date` (patrón SCD/snapshot).
La tabla `pl_monthly` ya tiene el P&L precomputado y filtrado — para la pregunta "muéstrame el P&L"
preferí `SELECT * FROM telco_demo.pl_monthly ORDER BY month` antes que recomputar de fuentes.
Insight CFO esperado al final: la MVNO necesita ~30% más revenue al costo actual, o ~25% menos payroll, para break-even.

Briefing completo (contexto + análisis adicionales que un CFO esperaría) en
docs/DEMO-FINANCIAL-CONSULTOR.md del repo galacticaia-gov. Para detalle por tabla usá
get_table_details (OM) — las descriptions del catálogo tienen el contexto granular.

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

6. GLOSARIO / NEGOCIO (keywords: qué significa, definición, glosario, dominio, jerarquía):
   - Paso 1: list_glossaries → ver glosarios raíz disponibles (NO inventar nombres como "Glosario de Negocio")
   - Paso 2: list_glossary_terms → ver términos jerárquicos. La salida agrupa por raíz y anida hijos bajo parent terms.
   - Lee el FQN para entender la jerarquía: TelcoLATAM.Finanzas.ARPU significa que ARPU es hijo del parent term Finanzas dentro del glosario raíz TelcoLATAM.
   - Si un término tiene marca "[parent term, N hijos]", úsalo como categoría/dominio en tu respuesta.
   - DONE con las definiciones

7. DISTRIBUCIÓN / AGRUPACIÓN (keywords: distribución, distribuyen, cuántos, ranking, por canal, por tipo):
   - Paso 1: search_catalog o get_table_details (OpenMetadata) → identificar tabla y columnas
   - Paso 2: execute_query con SQL completo → agrupar y contar TODOS los valores (NO usar LIMIT)
   - Paso 3 (si aplica): execute_query para contar nulls en la columna agrupada
   - Ejemplo de execute_query para distribución:
     TOOL: execute_query
     PARAMS: query=SELECT channel, COUNT(*) as n FROM telco_demo.recharges GROUP BY channel ORDER BY n DESC
   - Ejemplo para contar nulls:
     TOOL: execute_query
     PARAMS: query=SELECT COUNT(*) FILTER (WHERE channel IS NULL) as nulls, COUNT(*) as total FROM telco_demo.recharges
   - ⚠️ NUNCA uses LIMIT en queries de distribución — necesitas TODOS los valores
   - SOLO después de estos pasos → DONE

8. EVOLUCIÓN TEMPORAL (keywords: evolución, tendencia, cómo ha cambiado, por fecha):
   - Paso 1: get_table_details (OpenMetadata) → contexto
   - Paso 2: execute_query con SQL de agregación por fecha (SIN LIMIT, incluir TODAS las fechas)
   - Ejemplo:
     TOOL: execute_query
     PARAMS: query=SELECT usage_date, SUM(data_mb) as total_mb, AVG(data_mb) as avg_mb FROM telco_demo.usage_daily GROUP BY usage_date ORDER BY usage_date
   - SOLO después de ambos pasos → DONE

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
- Para execute_query: SIEMPRE escribe SQL completo con FROM y schema. Ejemplo:
  TOOL: execute_query
  PARAMS: query=SELECT col1, COUNT(*) as n FROM schema.tabla GROUP BY col1 ORDER BY n DESC
  NUNCA escribas solo "SELECT col" sin FROM — eso da error

Paso actual: {step}/{max_steps}
"""

            decision_response = self.llm.invoke([HumanMessage(content=decision_prompt)])
            decision = decision_response.content.strip()

            # Verificar si el LLM decide terminar.
            # Match estricto: "DONE" como única palabra de la última línea no vacía
            # (un substring match aceptaría "el paso anterior está done…" y cortaría
            # el loop antes de ejecutar el tool, llevando a alucinaciones).
            non_empty_lines = [ln.strip() for ln in decision.splitlines() if ln.strip()]
            if non_empty_lines and non_empty_lines[-1].upper() == "DONE":
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
                            # For execute_query, the query param may contain commas
                            # so take everything after "query=" as the value
                            if params_str.startswith("query="):
                                params["query"] = params_str.split("query=", 1)[1].strip()
                            else:
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
        is_stats = any(w in query_lower for w in ["estadísticas", "estadisticas", "stats"])
        is_viz = any(w in query_lower for w in ["gráfico", "grafico", "chart", "histograma", "barras", "distribución visual", "visualiza", "muestra gráfico"])
        is_quality = any(w in query_lower for w in ["calidad", "quality", "nulls", "nulos", "duplicados", "problemas", "reporte de calidad", "data quality"])
        is_analysis_detect = any(w in query_lower for w in ["qué análisis", "que analisis", "cómo analizo", "como analizo", "qué puedo hacer", "analizar", "explorar"])
        is_distribution = any(w in query_lower for w in ["distribuyen", "distribución", "distribucion", "ranking", "por canal", "por tipo", "por ciudad", "cuántos", "cuantos", "composición", "composicion", "segmento", "qué canal", "que canal", "más recargas", "mas recargas", "por qué canal", "por que canal"])
        is_temporal = any(w in query_lower for w in ["evolucion", "evolución", "tendencia", "cómo ha cambiado", "como ha cambiado", "por fecha", "temporal", "a lo largo"])

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
- Si hay 2+ numéricas → sugerir scatter plot (distribución bivariada descriptiva)
"""
        elif is_distribution:
            format_instructions = """
FORMATO PARA DISTRIBUCIÓN / AGRUPACIÓN:

### Distribución de [columna] en [tabla]

Muestra los resultados en tabla markdown con conteo y porcentaje:

| Valor | Conteo | % del Total |
|-------|--------|-------------|
| val1  | 150    | 45.5%       |
| val2  | 100    | 30.3%       |
| ...   | ...    | ...         |

### 💡 Insights automáticos
- Top 3 valores con % del total
- Regla de Pareto: si el 80% está en pocas categorías, mencionarlo
- Valor dominante: si un valor supera el 50%
- Si hay nulls en la columna agrupada, reportarlos como alerta 🔴
- Concentración geográfica o por segmento si aplica

OBLIGATORIO — Incluye al final un bloque viz con los datos reales:
```viz
type: bar_chart
col_name: nombre_columna
categories: val1,val2,val3
values: 150,100,80
title: Distribución de [columna]
```

Reglas:
- Usa bar_chart para categóricas (frecuencias)
- Incluye TODOS los valores, no solo el top 1
- Los valores deben venir de los resultados SQL — nunca inventes
"""
        elif is_temporal:
            format_instructions = """
FORMATO PARA EVOLUCIÓN TEMPORAL:

### Evolución de [métrica] en [tabla]

Muestra los datos por fecha en tabla markdown:

| Fecha | Valor | Variación vs anterior |
|-------|-------|-----------------------|
| 2026-03-21 | 1,234 | — |
| 2026-03-22 | 1,456 | +18.0% |

### 💡 Insights automáticos
- Tendencia general (crecimiento, decrecimiento, estable)
- Punto más alto y más bajo del período
- Variaciones significativas entre períodos consecutivos
- Si hay estacionalidad o patrones semanales

OBLIGATORIO — Incluye al final un bloque viz:
```viz
type: line_chart
col_name: nombre_metrica
x_values: 2026-03-21,2026-03-22,2026-03-23
y_values: 1234,1456,1300
x_label: Fecha
title: Evolución de [métrica]
```

Reglas:
- Usa line_chart para series temporales
- Los valores deben venir de los resultados SQL — nunca inventes
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
| 2 numéricas | age + revenue | Distribución bivariada | Scatter plot |
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

        format_prompt = f"""Eres DataGov Analyst, un agente de gobierno de datos. Has ejecutado {len(accumulated_context)} pasos para responder la pregunta del usuario.

{history_block}Pregunta actual: "{query}"

Datos obtenidos en {len(accumulated_context)} pasos:
{all_results}

INSTRUCCIONES GLOBALES:
- Responde siempre en español
- Si HISTORIAL DE CONVERSACIÓN PREVIA tiene contenido, NO te presentes ni saludes — responde directo al follow-up del usuario
- Tono sobrio y profesional: nada de "¡Hola!", "Soy tu Super Analista", ni adjetivos marketineros. Si te presentas (solo en el primer turno), una línea: "Soy DataGov Analyst, agente de gobierno de datos."
- Interpreta los datos: no solo números, sino qué significan para el negocio
- Usa el tipo estadístico de cada columna para dar contexto (numérica_continua → distribución; categórica → concentración)
- Siempre que tengas frecuencias o conteos, calcula el % sobre el total y menciona si hay concentración
- Si hay anomalías (>10% nulls, columna constante, outliers evidentes), menciónalas con 🔴
- No inventes datos — si no tienes la información, dilo y propón obtenerla
{format_instructions}
"""

        final_response = self.llm.invoke([HumanMessage(content=format_prompt)])
        return final_response.content


def create_agent() -> DataGovAgent:
    """Crear agente con los MCPs configurados."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))

    agent = DataGovAgent()

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

# Roadmap - DataGov Analyst

> Evolución progresiva: paso firme antes del siguiente.

---

## Arquitectura MCP — Principios

### No duplicar, consumir

DataGov Analyst NO reimplementa MCPs que ya existen en otros proyectos. Los consume como servidores externos.

```
┌─────────────────────────────────────────────────────────┐
│              DataGov Analyst Agent (cerebro)             │
│                   Orquesta LLM + MCPs                   │
└──────┬──────────────────┬───────────────────┬───────────┘
       │                  │                   │
       ▼                  ▼                   ▼
┌──────────────┐  ┌───────────────┐  ┌────────────────────┐
│ OpenMetadata │  │  SQL / DB     │  │  Futuro: más MCPs  │
│ MCP Server   │  │  MCP Server   │  │  (plug & play)     │
│              │  │               │  │                    │
│ EXTERNO:     │  │ Opciones:     │  │ - Snowflake        │
│ Viene de     │  │ a) sql_server │  │ - BigQuery         │
│ openmetadata-│  │    (custom)   │  │ - S3/GCS           │
│ mcp-agent    │  │ b) Google MCP │  │ - APIs REST        │
│ (repo separ.)│  │    Toolbox    │  │ - ...              │
└──────────────┘  └───────────────┘  └────────────────────┘
```

**Regla:** `openmetadata-mcp-agent` es el proyecto que evoluciona el MCP de gobierno.
DataGov Analyst lo consume — no lo copia. Un MCP, una fuente de verdad.

### Conexión a databases — Estrategia

**Hoy:** `sql_server.py` custom (FastMCP + psycopg2, READ-ONLY). Funciona para PostgreSQL.

**Futuro evaluado:** [Google MCP Toolbox for Databases](https://github.com/googleapis/genai-toolbox)
- MCP server open source especializado en databases
- Connection pooling, auth integrada, seguridad out-of-the-box
- Soporta múltiples databases con un solo servidor (PostgreSQL, MySQL, Spanner, AlloyDB, etc.)
- Configuración via YAML (`tools.yaml`), no código
- OpenTelemetry integrado (métricas + tracing)
- Versión actual: v0.28.0 (beta, pre-1.0)

**Decisión pendiente:** ¿Migrar `sql_server.py` a Google MCP Toolbox o mantener custom?
- **A favor de Toolbox:** escalabilidad a múltiples DBs sin escribir código, connection pooling pro, seguridad enterprise
- **A favor de custom:** control total, sin dependencia externa, ya funciona
- **Plan:** Evaluar Toolbox cuando se necesite agregar una segunda database. Para PostgreSQL solo, el custom es suficiente.

### Escalabilidad — Cómo agregar un MCP nuevo

```python
# En agent.py — 1 línea por MCP
agent.register_mcp("openmetadata", openmetadata_mcp)  # gobierno
agent.register_mcp("sql", sql_mcp)                    # queries PostgreSQL
# agent.register_mcp("bigquery", bq_mcp)              # futuro
# agent.register_mcp("toolbox", toolbox_mcp)           # Google MCP Toolbox (multi-DB)
```

Cada MCP es independiente. El agente descubre tools automáticamente via `discover_tools()`.
El LLM decide qué MCP y qué tool usar según la pregunta.

### Pendiente arquitectura

- [ ] Consumir OpenMetadata MCP como servidor externo (hoy es in-process, viene de `server.py` copiado)
- [ ] Evaluar Google MCP Toolbox for Databases cuando se necesite segunda DB
- [ ] Migrar orquestador de prompts de texto a function calling nativo (Gemini `google-genai`)
- [ ] Soporte para MCPs remotos (stdio → SSE/HTTP transport)

---

## Fase 1: Conocer y Describir los Datos

### 1.0 Setup ✅ (2026-02-13)
- [x] Base desde openmetadata-mcp-client (patrón probado)
- [x] CLAUDE.md con nueva visión
- [x] ROADMAP.md con subfases
- [x] README.md público actualizado
- [x] Estructura de archivos limpia
- [x] Arquitectura MCP plug & play (agent.py con register_mcp)
- [x] Multi-LLM: Gemini (enterprise) + OpenRouter (dev/testing)
- [ ] Puerto 4005 registrado en port-registry

### 1.1 Descubrimiento de datos ✅ (2026-02-13)
- [x] OpenMetadata MCP conectado y funcionando
- [x] Listar schemas, tablas, databases
- [x] Ver linaje de datos
- [x] Consultar glosario de negocio
- [x] El agente responde: "¿Qué datos tenemos?"
- [x] Probado: routing inteligente (preguntas de negocio → OpenMetadata)

### 1.2 MCP SQL ✅ (2026-02-13)
- [x] Evaluado: custom PostgreSQL MCP (más seguro y enfocado que supabase-community)
- [x] Integrado como segundo MCP plugin (sql_server.py)
- [x] Queries READ-ONLY enforced (keywords bloqueados)
- [x] El agente puede ejecutar SELECT contra las tablas reales
- [x] 5 tools: list_schemas, describe_table, get_column_stats, get_table_profile, execute_query

### 1.3 Perfil básico ✅ (2026-02-14)
- [x] Row count por tabla
- [x] Column count y tipos de datos
- [x] % nulls por columna
- [x] Cardinalidad (valores únicos)
- [x] Output tabular claro

### 1.3.5 Multi-Tool Reasoning ✅ (2026-02-14)
- [x] Refactorizar `process()` en agent.py para soportar multi-step reasoning
- [x] El LLM puede decidir llamar MÚLTIPLES tools en secuencia (2-5 pasos)
- [x] Cada paso acumula contexto: resultados anteriores se pasan al LLM para decidir el siguiente paso
- [x] El LLM puede decir "DONE" cuando tiene suficiente info para responder
- [x] Flujo: pregunta → step1 (tool call) → resultado1 → step2 (con contexto) → ... → DONE → respuesta final
- [x] Prompt orienta al agente a consultar OpenMetadata PRIMERO para entender esquema, luego SQL
- [x] Backward compatibility mantenida - preguntas simples siguen funcionando rápido
- [x] Safety limit de 5 tool calls máximo para evitar loops infinitos
- [x] Permite análisis complejos como: "describe tabla + estadísticas" o "relaciones + JOINs"

### 1.4 Clasificación de variables ✅
- [x] Clasificar automáticamente: numérica continua, discreta, categórica, temporal, ordinal, booleana, texto
- [x] La clasificación guía qué gráficos y análisis aplicar
- [x] Seguir árbol de decisión de data-to-viz.com

### 1.5 Estadísticas descriptivas + visualización ✅
- [x] Numéricas: min, max, avg, median, std, percentiles
- [x] Categóricas: frecuencias, moda, distribución
- [x] Gráficos con matplotlib según tipo de variable:
  - 1 numérica → histogram / density
  - 2 numéricas → scatter / boxplot
  - Categórica → bar chart
  - Numérica + Categórica → violin / boxplot por grupo
  - Temporal → line chart / connected scatter
- [x] Principios de Wilke: no distorsionar, proporción correcta

### 1.6 Top N e insights rápidos ✅
- [x] Top 3 valores más frecuentes por categórica
- [x] Valor más/menos repetido
- [x] "El 80% de X está en Y categorías"
- [x] Distribución de percentiles
- [x] Insights automáticos, solo estadística descriptiva

### 1.7 Detección de tipo de análisis ✅
- [x] Fecha + métrica → "Es análisis de tendencia"
- [x] Categórica vs numérica → "Es análisis de distribución por grupo"
- [x] 2 numéricas → "Es análisis de correlación"
- [x] Seguir árbol data-to-viz.com
- [x] El agente PROPONE qué tipo de análisis hacer

### 1.8 Data quality report ✅
- [x] % nulls por columna con semáforo (verde/amarillo/rojo)
- [x] Duplicados detectados
- [x] Outliers obvios (>3σ o 1.5*IQR)
- [x] Consistencia referencial entre tablas
- [x] Tipos de datos inconsistentes
- [x] Recomendaciones actionables

---

## Principio Rector

```
DataGov Analyst = Analista Descriptivo
```

**Alcance permanente: estadística descriptiva + visualización.**

Este agente entiende datos, los describe, detecta problemas de calidad y genera gráficos informativos.
**No hace clustering, predicciones, modelos, ni análisis inferencial.**

> La tentación de saltar a ML existe — resistirla es parte del diseño.

## Backlog congelado (2026-06-16 — proyecto en pausa)

> Issues cerrados para reducir ruido de tareas; retomar al reanudar el proyecto.
> El detalle completo vive en cada issue cerrado.

- [ ] **#23 [Epic] Enterprise Readiness for GalacticaGov Integration** — épica de readiness enterprise.
- [ ] **#24 Soporte multi-database vía MCP Toolbox (Google)** — conectar múltiples bases vía MCP Toolbox.
- [ ] **#32 Feedback CFO consultor sobre el briefing del demo telco** — tracking de ajustes pedidos.
- [ ] **#35 Migrar default LLM de Gemini 2.5 Pro a Kimi K2-0905** — cambio de modelo por defecto.

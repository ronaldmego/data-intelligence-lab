# Changelog - Khipu Analytics

## [0.7.0] - 2026-03-21

### Added
- Insights automáticos en perfiles de tabla: nulls altos 🔴, columnas constantes, valor dominante (>50%), regla de Pareto ([#10](https://github.com/ronaldmego/khipu-analytics/issues/10))
- Insights para estadísticas: top 3 con %, detección de sesgo (media vs mediana), outliers por IQR, percentil 90 ([#10](https://github.com/ronaldmego/khipu-analytics/issues/10))
- Format prompt global: calcula % sobre total siempre que hay frecuencias, alerta anomalías con 🔴 ([#10](https://github.com/ronaldmego/khipu-analytics/issues/10))

## [0.6.0] - 2026-03-21

### Added
- `viz.py` — módulo de visualización con 4 funciones: `plot_histogram`, `plot_bar_chart`, `plot_line_chart`, `plot_boxplot` ([#9](https://github.com/ronaldmego/khipu-analytics/issues/9))
- Gráficos siguen principios de Wilke: ejes desde 0, sin 3D, paleta colorblind-friendly, data-ink maximizado ([#9](https://github.com/ronaldmego/khipu-analytics/issues/9))
- `parse_viz_request()` y `render_viz()` — detectan bloque ```viz en respuesta del agente y generan figura ([#9](https://github.com/ronaldmego/khipu-analytics/issues/9))
- `app.py` renderiza figuras con `st.pyplot()` cuando el agente incluye un bloque viz ([#9](https://github.com/ronaldmego/khipu-analytics/issues/9))
- Format prompt actualizado: agente incluye bloque viz para preguntas de distribución, ranking, gráficos ([#9](https://github.com/ronaldmego/khipu-analytics/issues/9))
- `matplotlib` agregado a `requirements.txt` ([#9](https://github.com/ronaldmego/khipu-analytics/issues/9))

## [0.5.0] - 2026-03-21

### Added
- `classifier.py` — clasificador de variables con `classify_column()` y `classify_table()` ([#8](https://github.com/ronaldmego/khipu-analytics/issues/8))
- Tipos detectados: numérica_continua, numérica_discreta, categórica, temporal, booleana, identificador, constante, texto_libre, vacía ([#8](https://github.com/ronaldmego/khipu-analytics/issues/8))
- Cada clasificación incluye gráfico recomendado y estadísticas sugeridas según data-to-viz.com ([#8](https://github.com/ronaldmego/khipu-analytics/issues/8))
- `_extract_classifications()` en el agente: parsea output de `get_table_profile` y clasifica columnas automáticamente ([#8](https://github.com/ronaldmego/khipu-analytics/issues/8))
- Clasificaciones inyectadas en el format prompt para que el LLM mencione tipos estadísticos en sus respuestas ([#8](https://github.com/ronaldmego/khipu-analytics/issues/8))

## [0.4.0] - 2026-03-21

### Added
- Decision prompt con workflows explícitos por tipo de pregunta: perfil, stats, descubrimiento, linaje, glosario ([#7](https://github.com/ronaldmego/khipu-analytics/issues/7))
- Para perfil de tabla: exige 2 pasos mínimos (OpenMetadata + SQL), nunca responde con datos incompletos ([#7](https://github.com/ronaldmego/khipu-analytics/issues/7))
- Format prompt con detección de tipo de pregunta (`is_profile`, `is_stats`) y plantilla de respuesta específica ([#7](https://github.com/ronaldmego/khipu-analytics/issues/7))
- Perfil genera tabla markdown estructurada: columna | tipo | nulls% | únicos | observación ([#7](https://github.com/ronaldmego/khipu-analytics/issues/7))
- Instrucción explícita para extraer schema/table del FQN de OpenMetadata ([#7](https://github.com/ronaldmego/khipu-analytics/issues/7))

## [0.3.0] - 2026-03-21

### Fixed
- `strip_html()` utility elimina tags HTML de descripciones de OpenMetadata — `<p>`, `<br>`, `<strong>` ya no llegan crudas al agente ([#6](https://github.com/ronaldmego/khipu-analytics/issues/6))
- `api_get()` diferencia errores por status code: 404 / 401 / 500 / timeout / connect con mensajes accionables ([#6](https://github.com/ronaldmego/khipu-analytics/issues/6))
- Owner resolution en `get_table_details` soporta `owners[]` (OM reciente) y `owner{}` (OM legacy) con fallback ([#6](https://github.com/ronaldmego/khipu-analytics/issues/6))
- `execute_query` maneja errores psycopg2 específicos: `UndefinedTable`, `UndefinedColumn`, `SyntaxError` ([#6](https://github.com/ronaldmego/khipu-analytics/issues/6))
- `get_connection()` con mensajes descriptivos para errores de conexión (credenciales, DB no existe, servidor caído) ([#6](https://github.com/ronaldmego/khipu-analytics/issues/6))

## [0.2.0] - 2026-02-13

### Arquitectura MCP Plug & Play
- **agent.py**: Cerebro del agente con `register_mcp()` — cada fuente de datos es un plugin independiente
- Descubrimiento automático de tools de cada MCP conectado
- Futuro: agregar Snowflake/BigQuery con una línea

### SQL MCP (Fase 1.2)
- **sql_server.py**: 5 tools READ-ONLY contra PostgreSQL/Supabase
  - `list_schemas()` — schemas disponibles
  - `describe_table()` — estructura con tipos y row count
  - `get_column_stats()` — stats numéricas o frecuencias categóricas
  - `get_table_profile()` — perfil rápido de toda la tabla
  - `execute_query()` — SELECT libre (bloquea escritura)

### Multi-LLM
- Soporte Gemini (enterprise) + OpenRouter (dev/testing)
- Configurable via `LLM_PROVIDER` en `.env`
- 34 modelos gratis disponibles en OpenRouter

### Prompting Lab
- **prompting-lab.md**: Observaciones de comportamiento del agente
- 4 experimentos: el agente ruta bien sin obligarlo
- Preguntas de negocio → OpenMetadata, técnicas → SQL

### UI
- Rebranded a Khipu Analytics
- Sidebar muestra MCPs conectados y modelo activo

## [0.1.0] - 2026-02-13

### Base desde openmetadata-mcp-client
- Proyecto reescrito desde cero usando el agente de OpenMetadata exitoso
- OpenMetadata MCP: 6 tools (search, tables, details, lineage, databases, glossary)
- Streamlit chat UI
- Gemini 2.5 Pro como LLM
- Código anterior archivado en branch `archive/ml-express`
# CHANGELOG - Khipu Analytics

## 2026-02-14

### Fase 1.3.5 - Multi-Tool Reasoning ✅
- Refactorizado `agent.py` con método `process_multi_step()`
- El agente encadena 2-5 tool calls por pregunta
- Contexto acumulativo entre pasos
- OpenMetadata primero (contexto) → SQL después (datos reales)
- Safety limit: max 5 calls por pregunta
- Backward compatible con preguntas simples
- PR: https://github.com/ronaldmego/khipu-analytics/pull/5

### Fase 1.3 - Perfil Básico ✅
- Validado que tools existentes cubren todos los requerimientos
- get_table_profile: row count, column count, tipos, nulls%, cardinalidad
- get_column_stats: estadísticas detalladas por columna
- Documentación: PHASE_1_3_BASIC_PROFILE.md
- PR: https://github.com/ronaldmego/khipu-analytics/pull/4

### Fase 1.0-1.2 (previo)
- Setup base desde openmetadata-mcp-client
- OpenMetadata MCP conectado (6 tools)
- SQL MCP conectado (5 tools)
- Arquitectura plug & play con register_mcp()
- Multi-LLM: Gemini (enterprise) + OpenRouter (dev/testing)

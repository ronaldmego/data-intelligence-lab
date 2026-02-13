# Changelog - Khipu Analytics

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

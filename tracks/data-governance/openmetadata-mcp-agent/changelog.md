# Changelog

Todos los cambios notables de este proyecto se documentan aquí.

---

## [0.9.0] - 2026-03-02

### Added
- **Dry-run mode** — Sidebar toggle that intercepts write tool calls and shows what would be changed without executing. Read tools remain unaffected. ([#14](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/14))
- **Audit log** — All write operations (including dry-runs) are logged with timestamp, tool, args, and result. Displayed in the sidebar in reverse chronological order. Cleared with "Limpiar chat". ([#15](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/15))

---

## [0.8.0] - 2026-03-02

### Added
- **Classification & tag tools** — `create_classification`, `create_tag`, `assign_tag` allow creating tag categories, tags, and assigning them to tables. ([#12](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/12))
- **Domain creation tool** — `create_domain` creates data domains (Aggregate, Consumer Aligned, Source Aligned). Domain-to-table assignment deferred due to OM 1.11.7 PATCH limitation. ([#12](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/12))
- **Tag/domain instructions in SYSTEM_PROMPT** — Agent guided on classification→tag→assign workflow and domain types.

---

## [0.7.0] - 2026-03-02

### Added
- **Glossary management tools** — Three new tools: `create_glossary`, `create_glossary_term`, and `link_glossary_term` allow the agent to create glossaries, add terms with definitions and synonyms, and link terms to tables as tags. ([#10](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/10))
- **`api_post()` helper** — New HTTP helper in `server.py` for POST requests to create entities.
- **Glossary instructions in SYSTEM_PROMPT** — Agent guided on glossary creation workflow and term FQN format.

---

## [0.6.0] - 2026-03-02

### Added
- **Owner assignment tools** — Three new tools: `list_users`, `list_teams`, and `assign_owner` allow the agent to list available users/teams and assign owners to tables via PATCH. ([#8](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/8))
- **Owner instructions in SYSTEM_PROMPT** — Agent uses `list_users`/`list_teams` to show options when user doesn't specify an owner.

---

## [0.5.0] - 2026-03-02

### Added
- **Write tools: table & column descriptions** — Two new tools `update_table_description` and `update_column_description` allow the agent to update metadata in OpenMetadata via PATCH (JSON Patch RFC 6902). First write capabilities of the agent. ([#4](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/4))
- **`api_patch()` helper** — New HTTP helper in `server.py` for PATCH requests with `application/json-patch+json` content type.
- **Write safety in SYSTEM_PROMPT** — The agent now asks for user confirmation before executing any write operation, showing exactly what will change.
- **Column not found guidance** — If the user specifies a non-existent column, the tool returns the list of available column names.

---

## [0.4.0] - 2026-02-19

### Added
- **Memoria conversacional** - El agente inyecta los últimos 10 mensajes (5 turnos) del historial al contexto del LLM, permitiendo preguntas de seguimiento como "dime más sobre la primera" sin repetir el nombre de la tabla. ([#2](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/2))
- **Recuperación inteligente ante errores** - SYSTEM_PROMPT mejorado con estrategia de búsqueda explícita: si search_catalog falla, el agente intenta list_tables/list_databases como fallback, busca coincidencias parciales y encadena herramientas antes de rendirse. ([#3](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/3))

---

## [0.3.1] - 2026-02-19

### Fixed
- **Parseo de respuestas de Gemini** - Gemini 2.5 Pro a veces devuelve el contenido como lista de bloques `[{'type': 'text', 'text': '...', 'extras': {...}}]` en vez de string plano, causando que el chat mostrara JSON crudo. Agregada función `extract_text()` que maneja ambos formatos correctamente.

---

## [0.3.0] - 2026-02-13

### Changed
- **Function calling nativo de Gemini** - Reemplazado el routing manual (prompt de decisión + if/elif + parseo de strings) por `bind_tools()` nativo de langchain-google-genai. El agente ahora usa un loop conversacional donde Gemini decide qué tools llamar, puede encadenar varias, y reintentar si no encuentra resultados. ([#1](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/1))
- **Descubrimiento dinámico de tools** - Las tools se registran en una lista `TOOLS` y se bindean automáticamente. Para agregar una tool nueva solo hay que importarla y agregarla a la lista, sin tocar prompts ni routing.
- **Debug mejorado** - El expander ahora muestra la cadena completa de tools (Paso 1 → Paso 2 → ...) con args y resultado de cada una.
- **Tools visibles en sidebar** - Muestra dinámicamente cuántas y cuáles tools hay disponibles.

### Fixed
- Descripciones con tags HTML (`<p>...</p>`) ahora se limpian con `strip_html()` en todas las tools.
- Warning de pydantic por parámetro `schema` en `list_tables` resuelto renombrando a `schema_name`.

---

## [0.2.0] - 2026-02-13

### Added
- **Tool `list_domains()`** - Nuevo tool MCP que consulta `/api/v1/domains` de OpenMetadata para listar dominios y subdominios con tipo, descripción y jerarquía padre/hijo. ([#1](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/1))
- **Debug expander en UI** - Cada respuesta del agente ahora incluye un expander colapsable que muestra: tool usada, parámetros, decisión del LLM y resultado crudo de la API. Permite diagnosticar problemas de routing sin tocar código. ([#1](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/1))

### Fixed
- El agente ahora puede responder correctamente preguntas sobre dominios y subdominios del catálogo. Antes usaba `list_databases` como fallback. ([#1](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/1))

---

## [0.1.0] - 2026-02-12

### Added
- Chat UI con Streamlit
- Agente conversacional con Gemini 2.5 Pro
- 6 tools MCP: `search_catalog`, `list_tables`, `get_table_details`, `list_databases`, `get_lineage`, `list_glossary_terms`
- Configuración via `.env`
- Respuestas en español

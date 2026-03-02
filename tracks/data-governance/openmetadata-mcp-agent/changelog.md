# Changelog

Todos los cambios notables de este proyecto se documentan aquí.

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

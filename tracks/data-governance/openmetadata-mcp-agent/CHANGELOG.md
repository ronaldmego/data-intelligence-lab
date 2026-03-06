# Changelog

All notable changes to this project are documented here.

---

## [1.0.0] - 2026-03-02

### Added
- **Complete API coverage** — 8 new read tools: `list_stored_procedures`, `list_policies`, `list_roles`, `list_services`, `list_pipelines`, `list_dashboards`, `list_topics`, `list_data_products`. Total: 27 tools (17 read + 10 write). `server.py` is now the complete OpenMetadata connection layer. ([#17](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/17))
- `list_services` accepts a `service_type` parameter to query different service categories (database, messaging, dashboard, pipeline, mlmodel, storage, search).

---

## [0.9.0] - 2026-03-02

### Added
- **Dry-run mode** — Sidebar toggle that intercepts write tool calls and shows what would be changed without executing. Read tools remain unaffected. ([#14](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/14))
- **Audit log** — All write operations (including dry-runs) are logged with timestamp, tool, args, and result. Displayed in the sidebar in reverse chronological order. ([#15](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/15))

---

## [0.8.0] - 2026-03-02

### Added
- **Classification & tag tools** — `create_classification`, `create_tag`, `assign_tag` allow creating tag categories, tags, and assigning them to tables. ([#12](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/12))
- **Domain creation tool** — `create_domain` creates data domains (Aggregate, Consumer Aligned, Source Aligned). Domain-to-table assignment deferred due to OM 1.11.7 PATCH limitation. ([#12](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/12))
- **Tag/domain instructions in SYSTEM_PROMPT** — Agent guided on classification > tag > assign workflow and domain types.

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
- **Conversational memory** — The agent injects the last 10 messages (5 turns) of history into the LLM context, enabling follow-up questions like "tell me more about the first one" without repeating the table name. ([#2](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/2))
- **Smart error recovery** — Improved SYSTEM_PROMPT with explicit search strategy: if `search_catalog` fails, the agent tries `list_tables`/`list_databases` as fallback, searches for partial matches, and chains tools before giving up. ([#3](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/3))

---

## [0.3.1] - 2026-02-19

### Fixed
- **Gemini response parsing** — Gemini 2.5 Pro sometimes returns content as a list of blocks `[{'type': 'text', 'text': '...', 'extras': {...}}]` instead of a plain string, causing the chat to display raw JSON. Added `extract_text()` function that handles both formats correctly.

---

## [0.3.0] - 2026-02-13

### Changed
- **Native Gemini function calling** — Replaced manual routing (decision prompt + if/elif + string parsing) with native `bind_tools()` from langchain-google-genai. The agent now uses a conversational loop where Gemini decides which tools to call, can chain multiple tools, and retry if no results are found. ([#1](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/1))
- **Dynamic tool discovery** — Tools are registered in a `TOOLS` list and bound automatically. Adding a new tool only requires importing it and adding it to the list — no prompt or routing changes needed.
- **Improved debug** — The expander now shows the full tool chain (Step 1 > Step 2 > ...) with args and result for each call.
- **Tools visible in sidebar** — Dynamically shows how many and which tools are available.

### Fixed
- Descriptions with HTML tags (`<p>...</p>`) are now cleaned with `strip_html()` in all tools.
- Pydantic warning for `schema` parameter in `list_tables` resolved by renaming to `schema_name`.

---

## [0.2.0] - 2026-02-13

### Added
- **`list_domains()` tool** — New MCP tool that queries `/api/v1/domains` from OpenMetadata to list domains and subdomains with type, description, and parent/child hierarchy. ([#1](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/1))
- **Debug expander in UI** — Each agent response now includes a collapsible expander showing: tool used, parameters, LLM decision, and raw API result. Enables diagnosing routing issues without touching code. ([#1](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/1))

### Fixed
- The agent can now correctly answer questions about catalog domains and subdomains. Previously it used `list_databases` as a fallback. ([#1](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/1))

---

## [0.1.0] - 2026-02-12

### Added
- Chat UI with Streamlit
- Conversational agent with Gemini 2.5 Pro
- 6 MCP tools: `search_catalog`, `list_tables`, `get_table_details`, `list_databases`, `get_lineage`, `list_glossary_terms`
- Configuration via `.env`

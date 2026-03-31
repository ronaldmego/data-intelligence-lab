# Architecture — OpenMetadata Agent

## System Overview

Conversational AI agent that exposes OpenMetadata data catalog operations via natural language. Three layers: Streamlit UI, Gemini LLM with native function calling, and FastMCP tools that wrap the OpenMetadata REST API.

```
┌─────────────────────────────────────────────────┐
│                  User (Browser)                  │
└────────────────────┬────────────────────────────┘
                     │ HTTP
┌────────────────────▼────────────────────────────┐
│              Streamlit UI  (app.py)              │
│  - Chat interface                                │
│  - Sidebar: tools list, dry-run toggle, audit   │
│  - Conversation history (last 10 messages)       │
└────────────────────┬────────────────────────────┘
                     │ LangChain + bind_tools()
┌────────────────────▼────────────────────────────┐
│          Gemini 2.5 Pro  (app.py)               │
│  - Native function calling                       │
│  - Decides which tools to call and in sequence  │
│  - Conversational loop until final answer        │
└────────────────────┬────────────────────────────┘
                     │ Tool calls
┌────────────────────▼────────────────────────────┐
│          FastMCP Tools  (server.py)              │
│  27 tools: 17 read + 10 write                   │
│  - api_get(), api_patch(), api_post() helpers   │
│  - Dry-run mode intercepts write calls           │
│  - Audit log for all write operations            │
└────────────────────┬────────────────────────────┘
                     │ REST API + Bearer token
┌────────────────────▼────────────────────────────┐
│       OpenMetadata  (OPENMETADATA_URL)           │
│  - Tables, databases, schemas                    │
│  - Glossaries, tags, domains                     │
│  - Pipelines, dashboards, topics                 │
│  - Lineage, owners, descriptions                 │
└─────────────────────────────────────────────────┘
```

## Key Files

| File | Responsibility |
|------|---------------|
| `app.py` | Streamlit UI + Gemini agent + tool binding |
| `server.py` | All 27 FastMCP tools + HTTP helpers |
| `.env` | Credentials (GOOGLE_API_KEY, OPENMETADATA_URL, OPENMETADATA_TOKEN) |
| `requirements.txt` | Python dependencies |

## Tool Categories

| Category | Tools | Operations |
|----------|-------|-----------|
| Discovery | `search_catalog`, `list_databases`, `list_tables`, `get_table_details` | Read |
| Metadata | `list_glossary_terms`, `list_domains`, `list_tags` | Read |
| Extended read | `list_stored_procedures`, `list_policies`, `list_roles`, `list_services`, `list_pipelines`, `list_dashboards`, `list_topics`, `list_data_products` | Read |
| Lineage | `get_lineage` | Read |
| Users/Teams | `list_users`, `list_teams` | Read |
| Descriptions | `update_table_description`, `update_column_description` | Write |
| Ownership | `assign_owner` | Write |
| Glossary | `create_glossary`, `create_glossary_term`, `link_glossary_term` | Write |
| Tags | `create_classification`, `create_tag`, `assign_tag` | Write |
| Domains | `create_domain` | Write |

## Write Safety

All write tools require user confirmation via SYSTEM_PROMPT before executing. Dry-run mode (sidebar toggle) intercepts write calls and shows a preview without executing. Every write is logged in the audit log with timestamp, tool, args, and result.

## OpenMetadata Architecture

For OpenMetadata's internal architecture (Ingestion, Metadata Store, Elasticsearch), see [`docs/openmetadata-architecture.md`](./docs/openmetadata-architecture.md).

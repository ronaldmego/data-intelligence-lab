# Architecture - DataGov Analyst

## Overview

DataGov Analyst is a conversational data analyst agent built on a **MCP Plug & Play** architecture. The agent (brain) connects to data sources as independent plugins via the Model Context Protocol (MCP). Adding a new data source = one new MCP server + one `register_mcp()` call.

## Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Streamlit UI (app.py)                 │
│              Chat interface + matplotlib renders         │
└─────────────────────┬───────────────────────────────────┘
                      │ user messages / tool outputs
┌─────────────────────▼───────────────────────────────────┐
│                   Agent (agent.py)                       │
│         Gemini 2.5 Pro / OpenRouter (multi-LLM)         │
│         process_multi_step() — chains up to 5 calls      │
└──────────┬──────────────────────────┬───────────────────┘
           │                          │
┌──────────▼──────────┐   ┌───────────▼──────────────────┐
│  OpenMetadata MCP   │   │         SQL MCP               │
│     (server.py)     │   │      (sql_server.py)          │
│                     │   │                               │
│  search_catalog     │   │  list_schemas                 │
│  list_tables        │   │  describe_table               │
│  get_table_details  │   │  get_column_stats             │
│  get_lineage        │   │  get_table_profile            │
│  list_databases     │   │  execute_query (READ-ONLY)    │
│  list_glossary_terms│   │                               │
└──────────┬──────────┘   └───────────┬──────────────────┘
           │                          │
┌──────────▼──────────┐   ┌───────────▼──────────────────┐
│   OpenMetadata      │   │   PostgreSQL / Supabase       │
│   REST API          │   │   (external DB)               │
│   :8585             │   │                               │
└─────────────────────┘   └──────────────────────────────┘
```

## Key Files

| File | Responsibility |
|------|----------------|
| `app.py` | Streamlit UI — chat loop, renders matplotlib figures, sidebar |
| `agent.py` | Brain — LLM orchestration, MCP registration, multi-step reasoning |
| `server.py` | OpenMetadata MCP server — 6 tools via FastMCP |
| `sql_server.py` | SQL MCP server — 5 read-only tools via FastMCP |
| `viz.py` | Visualization module — matplotlib/seaborn, follows data-to-viz.com rules |
| `classifier.py` | Variable type classifier — decides which chart/stats to apply |

## Multi-Step Reasoning (Phase 1.3.5)

The `process_multi_step()` method in `agent.py` chains tool calls:

```
1. Agent receives question
2. Calls OpenMetadata MCP → gets governance context (what tables exist, tags, lineage)
3. Calls SQL MCP → gets real data (stats, distributions, samples)
4. Combines both contexts
5. Returns grounded answer
Safety limit: max 5 tool calls per question
```

## MCP Strategy

| MCP | When to use | What it provides |
|-----|-------------|-----------------|
| OpenMetadata | First, for context | Governance, lineage, glossary, ownership |
| SQL | After context established | Real data, distributions, statistics |

## Data Flow

```
User question
  → Agent decides tool strategy (multi-step)
  → OpenMetadata: "what data exists here?"
  → SQL: "what do the actual values look like?"
  → Gemini synthesizes both
  → Streamlit renders text + optional chart
```

## Multi-LLM Support

Configurable via `LLM_PROVIDER` in `.env`:
- `gemini` — Google Gemini 2.5 Pro (production)
- `openrouter` — OpenRouter (dev/testing, 34+ free models)

## Infrastructure

- **Runtime**: Python 3.10+, Streamlit
- **Port**: 4005 (Tailscale only, bind `<vps-host>`)
- **VPS**: GalacticaIA VPS
- **Access**: http://<vps-host>:4005

## Future Extensions (Plug & Play)

```python
# Adding a new data source = one line
agent.register_mcp("snowflake", snowflake_mcp_server)
agent.register_mcp("bigquery", bigquery_mcp_server)
```

# SKILL.md - OpenMetadata Integration

## Purpose

Provides conversational access to OpenMetadata data catalog operations.
Exposes 27 tools via MCP (Model Context Protocol) for discovery, governance, and metadata management.

## Tools Overview

### Discovery (Read)
- `search_catalog` — Full-text search across all assets
- `list_databases` — List available databases
- `list_tables` — Tables within a database/schema
- `get_table_details` — Full table metadata
- `list_glossary_terms` — Business glossary
- `list_domains` — Data domains
- `list_tags` — Classifications and tags

### Extended Discovery (Read)
- `list_stored_procedures`
- `list_policies`
- `list_roles`
- `list_services`
- `list_pipelines`
- `list_dashboards`
- `list_topics`
- `list_data_products`

### Lineage (Read)
- `get_lineage` — Upstream/downstream dependencies

### User Management (Read)
- `list_users`
- `list_teams`

### Metadata (Write)
- `update_table_description`
- `update_column_description`
- `assign_owner`

### Governance (Write)
- `create_glossary`
- `create_glossary_term`
- `link_glossary_term`
- `create_classification`
- `create_tag`
- `assign_tag`
- `create_domain`

## Architecture

```
┌─────────────────────────────────────┐
│  FastMCP Server (server.py)         │
│  - Tool registration                │
│  - Request routing                  │
│  - Error handling                   │
└──────────────┬──────────────────────┘
               │ REST API + Bearer
┌──────────────▼──────────────────────┐
│  OpenMetadata Instance              │
│  :8585                              │
└─────────────────────────────────────┘
```

## Configuration

Required environment variables:
- `OPENMETADATA_URL` — Base URL of OpenMetadata server
- `OPENMETADATA_TOKEN` — JWT authentication token

Optional:
- `DRY_RUN_MODE` — Intercept writes, show preview only

## Safety Features

1. **Dry-Run Mode** — All write tools check DRY_RUN_MODE first
2. **Audit Logging** — Every operation logged with context
3. **Confirmation Prompts** — Critical operations require explicit approval
4. **Segregation of Duties** — Enforced per DUTIES.md

## Dependencies

```
fastmcp
httpx
pydantic
```

## Entry Point

```python
# server.py
from fastmcp import FastMCP

mcp = FastMCP("openmetadata")

@mcp.tool()
def search_catalog(query: str) -> dict:
    ...
```

## Testing

```bash
# Test the MCP server
python skills/openmetadata/server.py

# Or use the GitAgent CLI (when available)
gitagent test skills/openmetadata
```

## Future Enhancements

- [ ] Data quality test integration
- [ ] Ingestion pipeline management
- [ ] Custom property support
- [ ] Bulk operations

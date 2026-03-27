# OpenMetadata MCP Agent

> A GitAgent-compliant conversational AI agent for OpenMetadata data catalog operations.

[![GitAgent](https://img.shields.io/badge/GitAgent-Compliant-blue)](https://github.com/open-gitagent/gitagent)
[![MCP](https://img.shields.io/badge/MCP-Protocol-green)]()
[![Compliance](https://img.shields.io/badge/Compliance-FINRA%20Ready-orange)]()

## What This Agent Does

Conversational interface to your OpenMetadata data catalog. 27 tools for:
- **Discovery** — Search tables, columns, glossaries
- **Governance** — Manage tags, domains, classifications  
- **Lineage** — Trace data dependencies
- **Stewardship** — Assign owners, update descriptions

## Quick Start

### Prerequisites

```bash
# Environment variables
export GOOGLE_API_KEY="your-google-api-key"
export OPENMETADATA_URL="http://your-om-host:8585"
export OPENMETADATA_TOKEN="your-jwt-token"
```

### Run with GitAgent (Recommended)

```bash
gitagent run .
```

### Run Standalone

```bash
# MCP Server only
python skills/openmetadata/server.py

# With Streamlit UI
streamlit run app.py
```

## GitAgent Structure

```
.
├── agent.yaml          # Manifest - models, compliance, skills
├── SOUL.md             # Agent identity and personality
├── DUTIES.md           # Segregation of duties policy
├── AGENTS.md           # Framework-agnostic fallback
├── skills/
│   └── openmetadata/
│       ├── SKILL.md    # Capability documentation
│       └── server.py   # MCP server (27 tools)
├── hooks/
│   ├── bootstrap.md    # Startup sequence
│   └── teardown.md     # Shutdown sequence
├── memory/
│   └── runtime/        # Session persistence
└── agents/             # Sub-agents (future)
```

## Safety First

This agent implements **enterprise-grade compliance**:

- ✅ **Segregation of Duties** — Roles conflict matrix enforced
- ✅ **Audit Logging** — Every operation traceable
- ✅ **Dry-Run Mode** — Test changes before applying
- ✅ **Approval Gates** — Critical operations require confirmation

See `DUTIES.md` for full compliance documentation.

## Tool Inventory

| Category | Count | Examples |
|----------|-------|----------|
| Discovery | 7 | search_catalog, list_tables, get_lineage |
| Metadata | 3 | update_table_description, assign_owner |
| Governance | 7 | create_glossary, assign_tag, create_domain |
| Extended | 10 | list_pipelines, list_dashboards, list_policies |

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   User Query    │────▶│  GitAgent    │────▶│  MCP Server     │
│   (Natural Lang)│     │  Runtime     │     │  (27 tools)     │
└─────────────────┘     └──────────────┘     └────────┬────────┘
                                                      │
                                            ┌─────────▼─────────┐
                                            │  OpenMetadata API │
                                            │  :8585            │
                                            └───────────────────┘
```

## Configuration

Edit `agent.yaml` to customize:

```yaml
model:
  provider: google
  model: gemini-2.5-pro
  
compliance:
  segregation_of_duties:
    enabled: true
    enforcement: strict
```

## Development

```bash
# Create a branch for agent changes
git checkout -b feat/new-metadata-tool

# Make changes to skills/openmetadata/
# Test locally
gitagent test skills/openmetadata

# PR and merge when ready
```

## Enterprise Usage

For FINRA/SEC compliance environments:

1. Enable strict SoD enforcement in `agent.yaml`
2. Configure audit log destination
3. Set up role-based access control
4. Enable dry-run mode for testing

See `DUTIES.md` for compliance configuration.

## License

MIT — See LICENSE file

## Links

- [GitAgent Specification](https://github.com/open-gitagent/gitagent)
- [OpenMetadata Documentation](https://docs.open-metadata.org/)
- [MCP Protocol](https://modelcontextprotocol.io/)

<p align="center">
  <img src="docs/logo.png" alt="OpenMetadata Agent" width="480"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/Streamlit-Chat_UI-FF4B4B?style=flat-square&logo=streamlit&logoColor=white"/>
  <img src="https://img.shields.io/badge/Gemini-2.5_Pro-4285F4?style=flat-square&logo=google&logoColor=white"/>
  <img src="https://img.shields.io/badge/MCP-27_Tools-39d353?style=flat-square"/>
  <img src="https://img.shields.io/badge/OpenMetadata-v1.3+-blue?style=flat-square"/>
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=flat-square"/>
</p>

<p align="center">
  <strong>A conversational AI assistant for your data catalog.</strong><br/>
  Ask questions in natural language — get answers from OpenMetadata. No UI, no API calls, just chat.
</p>

---

<p align="center">
  <img src="docs/screenshots/01-hero.png" alt="OpenMetadata Agent in action" width="800"/>
</p>

---

## The Problem

Data catalogs like OpenMetadata are powerful, but most business users never open them. They don't know the UI, don't know where to look, and definitely don't write API calls. The metadata stays locked behind a tool that only engineers use.

## The Solution

OpenMetadata Agent adds a **conversational layer** on top of your data catalog. Users ask questions in plain language — the agent queries the catalog automatically using 27 MCP tools and Gemini's native function calling.

```
User: "What tables do we have related to customers?"
Agent: searches catalog → finds 3 tables → returns details with columns and descriptions
```

No need to learn the OpenMetadata UI. No API calls. Just ask.

---

## See It in Action

**List and explore tables:**

![OpenMetadata Agent — List tables in telco_demo schema](docs/demos/01-list-tables.gif)

**Query the business glossary:**

![Glossary lookup — "What does Data Owner mean?"](docs/demos/02-glossary.gif)

**Find table owners:**

![Owner query — "Who owns the customers table?"](docs/demos/03-owner.gif)

---

## Quick Start

```bash
git clone https://github.com/ronaldmego/openmetadata-mcp-agent.git
cd openmetadata-mcp-agent

cp .env.example .env
# Edit .env with your credentials (see Environment Variables below)

pip install -r requirements.txt

streamlit run app.py --server.port 4004
# Open http://localhost:4004
```

### Prerequisites

- Python 3.10+
- A running **OpenMetadata instance** (v1.3+) — [Docker quickstart](https://docs.open-metadata.org/deployment/docker) or use the [OpenMetadata Sandbox](https://sandbox.open-metadata.org/)
- A **Google Gemini API key** — free at [Google AI Studio](https://aistudio.google.com/apikey)

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Streamlit     │────▶│   Agent         │────▶│  OpenMetadata   │
│   Chat UI       │     │   (Gemini LLM)  │     │  REST API       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │
        ▼                       ▼
   User                 27 MCP Tools
   (browser)            (17 read + 10 write)
```

### How It Works

1. User asks a question in the chat UI
2. Gemini analyzes the question and decides which MCP tool(s) to call
3. The agent executes the tool against the OpenMetadata REST API
4. Gemini formats a human-readable answer from the raw result
5. If the first tool doesn't return useful results, the agent retries with alternative strategies

No manual routing or keyword matching — Gemini's native function calling handles everything automatically.

Every tool call is visible in a debug expander:

![Tool trace showing args and raw API result](docs/screenshots/03-tool-trace.png)

---

## Available Tools (27)

### Read Tools (17)

| Tool | Description |
|------|-------------|
| `search_catalog` | Search assets by keyword |
| `list_tables` | List tables with optional database/schema filter |
| `get_table_details` | Full table details: columns, types, owner, tags |
| `get_lineage` | Upstream and downstream data lineage |
| `list_databases` | List all registered databases |
| `list_glossary_terms` | Business glossary terms and definitions |
| `list_domains` | Data domains and subdomains |
| `list_stored_procedures` | Stored procedures by schema |
| `list_policies` | Access policies and rule counts |
| `list_roles` | Roles with associated policies |
| `list_services` | Services by type (database, messaging, dashboard, pipeline, mlmodel, storage, search) |
| `list_pipelines` | Data pipelines and their services |
| `list_dashboards` | Dashboards and their services |
| `list_topics` | Kafka/messaging topics |
| `list_data_products` | Data products and their domains |
| `list_users` | Registered users |
| `list_teams` | Registered teams |

### Write Tools (10)

| Tool | Description |
|------|-------------|
| `update_table_description` | Update a table's description |
| `update_column_description` | Update a column's description |
| `assign_owner` | Assign a user or team as table owner |
| `create_glossary` | Create a new business glossary |
| `create_glossary_term` | Add a term to a glossary |
| `link_glossary_term` | Link a glossary term to a table |
| `create_classification` | Create a tag classification (category) |
| `create_tag` | Create a tag within a classification |
| `assign_tag` | Assign a tag to a table |
| `create_domain` | Create a data domain |

### Safety Features

- **Dry-run mode** — Toggle in sidebar to preview write operations without applying changes
- **Confirmation prompt** — Agent always asks before executing any write operation
- **Audit log** — All write operations logged with timestamp, tool, args, and result

---

## Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| **UI** | Streamlit | Fast prototyping, built-in chat components |
| **LLM** | Google Gemini 2.5 Pro | Native function calling, strong reasoning |
| **Tools** | FastMCP | Standard MCP protocol for tool definitions |
| **Backend** | OpenMetadata REST API | Open-source data catalog |
| **Language** | Python 3.10+ | Ecosystem compatibility |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

| Variable | Description | Required |
|----------|-------------|----------|
| `GOOGLE_API_KEY` | Gemini API key ([get one here](https://aistudio.google.com/apikey)) | Yes |
| `OPENMETADATA_URL` | Your OpenMetadata instance URL | Yes |
| `OPENMETADATA_TOKEN` | JWT token from OpenMetadata (Settings > Bots) | Yes |
| `GEMINI_MODEL` | Model to use (default: `gemini-2.5-pro`) | No |

---

## Project Structure

```
openmetadata-mcp-agent/
├── app.py              # Streamlit UI + agent (Gemini function calling)
├── server.py           # MCP tool definitions (OpenMetadata API) — 27 tools
├── .env.example        # Configuration template
├── requirements.txt    # Python dependencies
├── ROADMAP.md          # Development roadmap
├── CHANGELOG.md        # Version history
├── CONTRIBUTING.md     # Contribution guidelines
└── scripts/            # Test and utility scripts
```

---

## Example Prompts

```
"What tables do we have?"
"Show me the lineage of the orders table"
"What columns does the customers table have?"
"Search everything related to sales"
"What databases are registered?"
"Show me the business glossary"
"What data domains exist?"
"Update the customers table description"       → asks for confirmation
"Assign admin as owner of the orders table"    → asks for confirmation
"Create a glossary called 'business terms'"    → asks for confirmation
```

---

## Testing

```bash
# Test OpenMetadata connection and MCP tools
python scripts/test_queries.py

# Test the full agent pipeline
python scripts/test_agent_gemini.py
```

---

## Roadmap

See [ROADMAP.md](./ROADMAP.md) for the full development plan.

This project is a **single-user MVP/POC** with complete API coverage (27 tools). It serves as the reusable foundation for a future enterprise edition with multi-user sessions, SSO, and production deployment.

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](./LICENSE)

---

Built by [Ronald Mego](https://ronaldmego.com) · [GalacticaIA](https://galacticaia.com)

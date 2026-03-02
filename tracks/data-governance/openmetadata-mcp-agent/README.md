# OpenMetadata Agent

> A conversational AI assistant for your data catalog. Ask questions in natural language, get answers from OpenMetadata.

<!-- TODO: Add screenshot of the chat UI here -->
<!-- ![OpenMetadata Agent Screenshot](docs/screenshot.png) -->

## The Problem

Data catalogs like OpenMetadata are powerful, but most business users never open them. They don't know the UI, they don't know where to look, and they definitely don't write API calls. The metadata stays locked behind a tool that only engineers use.

## The Solution

OpenMetadata Agent adds a **conversational layer** on top of OpenMetadata. Users ask questions in plain language and the agent queries the catalog automatically using MCP tools and Gemini's native function calling.

```
User: "What tables do we have related to customers?"
Agent: searches catalog → finds 3 tables → returns details with columns and descriptions
```

No need to learn the OpenMetadata UI. No need to write API calls. Just ask.

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

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Streamlit     │────▶│   Agent         │────▶│  OpenMetadata   │
│   Chat UI       │     │   (Gemini LLM)  │     │  REST API       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │
        ▼                       ▼
   User                 MCP Tools:
   (browser)            - search_catalog
                        - list_tables
                        - get_table_details
                        - get_lineage
                        - list_databases
                        - list_glossary_terms
                        - list_domains
```

## How It Works

1. User asks a question in the chat UI
2. Gemini analyzes the question and decides which MCP tool(s) to call
3. The agent executes the tool against the OpenMetadata REST API
4. Gemini receives the raw result and formats a human-readable answer
5. If the first tool doesn't return useful results, the agent retries with alternative strategies

No manual routing or keyword matching — Gemini's native function calling handles tool selection automatically.

## Available Tools

| Tool | Description |
|------|-------------|
| `search_catalog` | Search assets by keyword |
| `list_tables` | List tables with optional database/schema filter |
| `get_table_details` | Full table details: columns, types, owner, tags |
| `get_lineage` | Upstream and downstream data lineage |
| `list_databases` | List all registered databases |
| `list_glossary_terms` | Business glossary terms and definitions |
| `list_domains` | Data domains and subdomains |

> **Note:** All tools are currently read-only. Write operations (add descriptions, manage glossary, assign tags) are planned for Phase 2 — see [ROADMAP.md](./ROADMAP.md).

## Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| **UI** | Streamlit | Fast prototyping, built-in chat components |
| **LLM** | Google Gemini 2.5 Pro | Native function calling, good reasoning |
| **Tools** | FastMCP | Standard MCP protocol for tool definitions |
| **Backend** | OpenMetadata REST API | Open-source data catalog |
| **Language** | Python 3.10+ | Ecosystem compatibility |

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

| Variable | Description | Required |
|----------|-------------|----------|
| `GOOGLE_API_KEY` | Gemini API key ([get one here](https://aistudio.google.com/apikey)) | Yes |
| `OPENMETADATA_URL` | Your OpenMetadata instance URL | Yes |
| `OPENMETADATA_TOKEN` | JWT token from OpenMetadata (Settings > Bots) | Yes |
| `GEMINI_MODEL` | Model to use (default: `gemini-2.5-pro`) | No |

## Project Structure

```
openmetadata-mcp-agent/
├── app.py              # Streamlit UI + agent (Gemini function calling)
├── server.py           # MCP tool definitions (OpenMetadata API)
├── .env.example        # Configuration template
├── requirements.txt    # Python dependencies
├── ROADMAP.md          # Development roadmap
├── changelog.md        # Version history
└── test_*.py           # Test scripts
```

## Testing

```bash
# Test OpenMetadata connection and MCP tools
python test_queries.py

# Test the full agent pipeline
python test_agent_gemini.py
```

## Conversation Examples

```
"What tables do we have?"                    → list_tables
"Show me the lineage of the orders table"    → get_lineage("orders")
"What columns does the customers table have?" → get_table_details("customers")
"Search everything related to sales"          → search_catalog("sales")
"What databases are registered?"              → list_databases
"Show me the business glossary"               → list_glossary_terms
"What data domains exist?"                    → list_domains
```

## Roadmap

See [ROADMAP.md](./ROADMAP.md) for the full development plan. Key upcoming features:

- **Write operations** — Add descriptions, manage glossary, assign tags and owners
- **Multi-tool chaining** — Agent chains multiple tools per question
- **Multi-user sessions** — Per-user history and rate limiting
- **Authentication** — SSO, roles, granular permissions

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

## License

[MIT](./LICENSE)

---

Built by [GalacticaIA](https://galacticaia.com)

<p align="center">
  <img src="docs/logo.png" alt="DataGov Analyst" width="480"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/Streamlit-Chat_UI-FF4B4B?style=flat-square&logo=streamlit&logoColor=white"/>
  <img src="https://img.shields.io/badge/OpenMetadata-Catalog-blue?style=flat-square"/>
  <img src="https://img.shields.io/badge/MCP-FastMCP-39d353?style=flat-square"/>
  <img src="https://img.shields.io/badge/LLM-Gemini_%7C_OpenRouter-4285F4?style=flat-square&logo=google&logoColor=white"/>
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=flat-square"/>
</p>

<p align="center">
  <strong>AI-powered data analyst that <em>understands your data before analyzing it</em></strong><br/>
  Combines data governance context with real SQL exploration — 100% local, 100% open source.
</p>

---

## Compatibility

**Tested against:** OpenMetadata `1.11.7`  
**Target instances:**
- `demo-openmetadata` (OM 1.11.7 vanilla) — instancia de referencia
- `gov-galacticaia` (OM 1.12.0-SNAPSHOT fork) — producto propio

> **⚠️ Version Dependency:** This agent was built and tested against OpenMetadata 1.11.7. Before upgrading the target OM instance, verify API compatibility.
>
> **MCP Tools:** OpenMetadata MCP (6 tools) + SQL MCP (5 tools, read-only)

---

<p align="center">
  <img src="docs/datagov-demo.gif" alt="DataGov Analyst Demo" width="800"/>
</p>

---

## The Problem

Data analysts spend most of their time figuring out *what data exists* before they can analyze it. They switch between catalog tools, SQL clients, and documentation — losing context at every step.

Generic AI agents make this worse: they execute queries and generate charts, but they don't know **who owns the table**, whether the data passed quality tests, or what "status = 3" means in your business.

## The Solution

DataGov Analyst connects to your **data catalog** (OpenMetadata) and your **database** (PostgreSQL/Supabase) simultaneously. It reads table descriptions, ownership, tags, lineage, and business glossary *before* running any SQL — so every analysis starts with context.

> **Analytics without governance is like diagnosing without medical history.**

### What it does
- Consults the governed catalog **before** touching the data
- Profiles tables automatically (structure + real statistics in one step)
- Classifies variables by statistical type (continuous, discrete, categorical, temporal)
- Generates the right chart for each data type (following [data-to-viz.com](https://data-to-viz.com))
- Detects data quality issues (nulls, constants, skewed distributions)
- Speaks SQL — you ask in natural language, it writes and runs queries

### What it doesn't do (by design)
- No predictions, no ML, no clustering — purely descriptive analytics
- No data modification — all SQL is read-only

---

## Quick Start

```bash
git clone https://github.com/ronaldmego/agent-data-analyst.git
cd agent-data-analyst

cp .env.example .env
# Edit .env with your credentials (see Environment Variables below)

pip install -r requirements.txt

streamlit run app.py --server.port 4005
# Open http://localhost:4005
```

### Requirements

- Python 3.10+
- An [OpenMetadata](https://open-metadata.org/) instance (URL + JWT token)
- A PostgreSQL or Supabase database
- An LLM API key: [Google Gemini](https://ai.google.dev/) or [OpenRouter](https://openrouter.ai/) (free tier available)

---

## How It Works

1. **You ask** a question in natural language (e.g., *"Profile the customers table"*)
2. **OpenMetadata first** — gets table description, owner, tags, lineage, glossary context
3. **SQL second** — runs read-only queries for real statistics, distributions, profiles
4. **Combines both** — delivers structured insights with charts and anomaly detection

### Real Example

```
→ "How are customers distributed by customer_type?"
← Verified lineage, glossary and business terms before touching data.
← Found something unexpected: catalog said "95% prepaid".
   Real data: 45% postpaid · 30% prepaid · 25% hybrid.
← Verdict: "Metadata is outdated. Recommend reviewing with the table owner."
```

It didn't just analyze data — it **audited reality against the catalog** and found the discrepancy.

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Streamlit     │────▶│   Agent Core    │────▶│  OpenMetadata   │
│   Chat UI       │     │  (LLM + MCP)    │     │  REST API       │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 └──────────────▶┌─────────────────┐
                                                 │  PostgreSQL /   │
                                                 │  Supabase (SQL) │
                                                 └─────────────────┘
                          MCP Tools:
                          ├── OpenMetadata MCP
                          │   search, tables, details,
                          │   lineage, glossary
                          │
                          └── SQL MCP (read-only)
                              execute_query, describe,
                              stats, profile
```

### Plug & Play MCP Architecture

Each data source is an independent **MCP (Model Context Protocol)** plugin. The agent discovers tools automatically — adding a new source is one line of code:

```python
agent.register_mcp("snowflake", snowflake_mcp)  # that's it
```

Zero hardcoded tools. Each MCP has its own connection, its own tools, and can be replaced or updated independently.

---

## Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| UI | Streamlit | Rapid chat interface with inline charts |
| LLM | Gemini 2.5 Pro / OpenRouter | Multi-provider support (paid + free options) |
| Catalog | OpenMetadata (via MCP) | Governance-aware: descriptions, tags, lineage |
| Database | PostgreSQL / Supabase (via MCP) | Direct SQL for real statistics |
| Visualization | matplotlib + seaborn | Follows Wilke's data visualization principles |
| Protocol | FastMCP | Plug & play data source architecture |

## What Makes It Different

| Feature | Generic SQL chatbots | DataGov Analyst |
|---------|---------------------|-----------------|
| Data context | None — just runs SQL | OpenMetadata catalog (descriptions, owners, tags, lineage) |
| Variable classification | None | Auto-classifies columns (continuous, discrete, categorical, temporal) |
| Chart selection | Random or user-chosen | Automatic based on variable type |
| Data quality | Not covered | Built-in quality reports with traffic-light indicators |
| Extensibility | Hardcoded connectors | MCP plug & play — add any data source in one line |

---

## Project Structure

```
agent-data-analyst/
├── app.py              # Streamlit chat UI
├── agent.py            # Agent core — LLM + MCP orchestration
├── server.py           # OpenMetadata MCP server (6 tools)
├── sql_server.py       # SQL MCP server (5 tools, read-only)
├── viz.py              # Visualization module (matplotlib)
├── classifier.py       # Statistical variable type classifier
├── .env.example        # Environment variables template
├── requirements.txt    # Python dependencies
└── pyproject.toml      # Project config + linter (ruff)
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Description | Required |
|----------|-------------|----------|
| `GOOGLE_API_KEY` | Gemini API key | If using Gemini |
| `OPEN_ROUTER_API_KEY` | OpenRouter API key | If using OpenRouter |
| `LLM_PROVIDER` | `gemini` or `openrouter` | Yes |
| `GEMINI_MODEL` | Gemini model name | If using Gemini |
| `OPENROUTER_MODEL` | OpenRouter model name | If using OpenRouter |
| `OPENMETADATA_URL` | OpenMetadata instance URL | Yes |
| `OPENMETADATA_TOKEN` | OpenMetadata JWT token | Yes |
| `SUPABASE_DB_HOST` | Database host | Yes |
| `SUPABASE_DB_PORT` | Database port | Yes |
| `SUPABASE_DB_USER` | Database user | Yes |
| `SUPABASE_DB_PASSWORD` | Database password | Yes |
| `SUPABASE_DB_NAME` | Database name | Yes |

---

## Example Prompts

```
What tables do we have?
Profile the customers table in telco_demo
How are customers distributed by channel?
Show me the data quality report for usage_daily
What analysis can I do with the recharges table?
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE) - Ronald Mego

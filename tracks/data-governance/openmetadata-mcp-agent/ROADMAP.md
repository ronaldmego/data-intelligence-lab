# Roadmap - OpenMetadata Agent

## MVP (Current) ✅

- [x] Chat UI with Streamlit
- [x] Agent with Gemini 2.5 Pro (native function calling)
- [x] 7 read-only tools: search, tables, details, lineage, databases, glossary, domains
- [x] Configuration via .env
- [x] Debug expander in UI (view tool used, parameters, raw result)

## Phase 1.5: Smart Agent ✅

- [x] Dynamic tool discovery from MCP server
- [x] Native function calling (no manual routing)
- [x] Retry loop with alternative strategies
- [x] Conversational memory ([#2](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/2))
- [x] Smart error recovery ([#3](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/3))
- [x] Multi-tool per query — agent chains tools via Gemini's native function calling loop
- [x] Complete API coverage — 8 new read tools (storedProcedures, policies, roles, services, pipelines, dashboards, topics, dataProducts). server.py is now the full connection layer. ([#17](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/17))

## Phase 2: Write Operations ✅

Enable the agent to **write metadata** to OpenMetadata, not just read it.

### Metadata Enrichment
- [x] **Add/edit table descriptions** — PATCH table metadata with natural language ([#4](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/4))
- [x] **Add/edit column descriptions** — PATCH column-level descriptions ([#4](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/4))
- [x] **Assign owners** to tables and assets — PATCH owner field ([#8](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/8))

### Glossary Management
- [x] **Create glossary** — POST new glossary ([#10](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/10))
- [x] **Create glossary terms** — POST terms with definitions and synonyms ([#10](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/10))
- [x] **Link glossary terms to assets** — Associate terms with tables/columns ([#10](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/10))

### Classification & Organization
- [x] **Create/assign tags** — POST tags and PATCH them onto assets ([#12](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/12))
- [x] **Create/assign domains** — POST domains; table assignment deferred (OM 1.11.7 PATCH limitation) ([#12](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/12))

### Safety
- [x] Confirmation prompt before any write operation ([#4](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/4))
- [x] Dry-run mode to preview changes before applying ([#14](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/14))
- [x] Audit log of all write operations ([#15](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/15))

## Phase 2.5: Data Quality & Observability ([#19](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/19))

Enable the agent to **surface data quality issues** — the biggest gap in current coverage.

### Read tools (priority)
- [ ] **`list_test_suites`** — List all test suites with pass/fail/aborted summary counts
- [ ] **`list_test_cases`** — List test cases, filterable by table FQN, suite, and status (Success/Failed/Aborted)
- [ ] **`get_test_case_results`** — Historical results for a specific test case (last N days)
- [ ] **`get_failed_tests`** — Quick view: all currently failing tests across the catalog

### Write tools (future)
- [ ] **`create_test_suite`** — Create a test suite for a table
- [ ] **`add_test_case`** — Add a test case (columnValuesNotNull, tableRowCountToBeBetween, etc.)

### Ingestion Pipeline Monitoring ([#20](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/20))
- [ ] **`list_ingestion_pipelines`** — List ingestion pipelines with last run status, filterable by service and type
- [ ] **`get_ingestion_pipeline_status`** — Run history for a specific pipeline (last N runs)
- [ ] **`get_pipeline_filters`** — Inspect table/schema filters and profile sample % of a pipeline

### API endpoints
- `/api/v1/dataQuality/testSuites` — suites with summary
- `/api/v1/dataQuality/testCases` — cases filterable by status, entity
- `/api/v1/dataQuality/testCases/{fqn}/testCaseResult` — historical results
- `/api/v1/services/ingestionPipelines` — ingestion pipelines (filterable by service, type)
- `/api/v1/services/ingestionPipelines/{id}/pipelineStatus` — run history

### Why
- "What tests are failing?" is the most natural question for a data steward
- "Did the Oracle profiler run ok?" replaces SSH + manual log grepping
- Currently requires navigating the OM UI or SSH to the server manually
- Closes the biggest gap vs full OM API coverage (see [yangkyeongmo/mcp-server-openmetadata](https://github.com/yangkyeongmo/mcp-server-openmetadata) for reference)

## Phase 3: Multi-Agent Architecture (Idea 💡)

**Concept:** Multiple specialized agents consuming a single centralized MCP governance server, instead of spinning up separate MCP server instances per user/agent.

### Architecture Vision
```
                    ┌─────────────────────┐
                    │  OpenMetadata MCP    │
                    │  Server (central)    │
                    │  server.py via SSE   │
                    └─────────┬───────────┘
                              │ MCP Protocol (SSE)
              ┌───────────────┼───────────────┐
              │               │               │
        ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐
        │ Agent: DQ  │  │ Agent:    │  │ Agent:    │
        │ Steward    │  │ Lineage   │  │ Glossary  │
        │            │  │ Explorer  │  │ Manager   │
        └────────────┘  └───────────┘  └───────────┘
```

### Why
- Current approach: each `app.py` imports `server.py` functions directly (Python import, no MCP protocol)
- Problem at scale: N agents = N server instances, each with its own connection to OpenMetadata
- Solution: One MCP server exposed via SSE, multiple agents connect as clients
- Agents can be specialized by domain (Data Quality, Lineage, Glossary, Compliance) while sharing the same governance toolset
- Uses **mcp-use** or equivalent client library for agent ↔ MCP server communication

### Key Decisions (TBD)
- [ ] SSE vs stdio for multi-client support (SSE preferred for network access)
- [ ] Auth/session isolation per agent
- [ ] Tool-level RBAC: which agents can use write tools vs read-only
- [ ] Orchestrator agent vs independent agents with shared context

## Future: Enterprise Edition (separate project)

Phases 3-6 involve multi-user, authentication, enterprise audit, and production hardening.
These are **out of scope for this project**, which serves as a single-user MVP/POC.

This project's `server.py` is designed to be the **complete, reusable OpenMetadata connection layer** — once [#17](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/17) is done, the enterprise project inherits it as-is.

A separate enterprise project will take this codebase as a starting point and rearchitect for:
- Multi-tenancy and per-user sessions
- SSO/OIDC authentication and role-based authorization
- Persistent audit logs with IT manager dashboards
- Integrations (Microsoft Teams, Slack webhooks)
- Production deployment (Docker, health checks, rate limiting)

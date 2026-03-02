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
- [ ] Multi-tool per query — agent can chain multiple tools in one question
- [ ] Full API coverage — tools for: data products, tags, policies, teams, users, pipelines

## Phase 2: Write Operations 🚧

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
- [ ] Dry-run mode to preview changes before applying ([#14](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/14))
- [ ] Audit log of all write operations ([#15](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/15))

## Phase 3: Multi-User

- [ ] Per-user sessions (Streamlit session state)
- [ ] Persistent conversation history
- [ ] Request limits per session
- [ ] Per-user query logging

## Phase 4: Authentication & Authorization

- [ ] Login with username/password
- [ ] SSO integration (SAML/OIDC)
- [ ] Roles: admin, analyst, viewer
- [ ] Granular permissions by schema/database

## Phase 5: Enterprise Audit

- [ ] Full query audit log
- [ ] Usage dashboard (queries per user, per day)
- [ ] Sensitive query alerts
- [ ] Log export for compliance
- [ ] SIEM integration

## Phase 6: Production Hardening

- [ ] Optimized Dockerfile
- [ ] Docker Compose with nginx/traefik
- [ ] Health checks
- [ ] Rate limiting
- [ ] Response caching
- [ ] Configuration backup

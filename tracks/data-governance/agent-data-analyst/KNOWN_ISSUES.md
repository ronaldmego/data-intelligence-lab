# Known Issues - DataGov Analyst

## Active Limitations

### MCP Connection Lifecycle
- **Issue**: MCP servers (OpenMetadata, SQL) are initialized at app startup. If the external service goes down, the agent fails silently or returns unhelpful errors.
- **Workaround**: Restart Streamlit (`Ctrl+C` and rerun) to reinitialize MCP connections.
- **Status**: Deferred — low priority for single-user internal tool.

### No Persistent Chat History
- **Issue**: Conversation history is stored in Streamlit session state only. Refreshing the browser resets the entire chat.
- **Workaround**: None — by design for now (stateless sessions).
- **Status**: Deferred — would require Supabase integration for persistence.

### Multi-Step Reasoning Cap
- **Issue**: `process_multi_step()` has a hard cap of 5 tool calls per question. Complex analytical questions that require more steps may return incomplete answers.
- **Workaround**: Break complex questions into smaller sub-questions.
- **Status**: Intentional safety limit. Revisit in Phase 1.4+.

### OpenRouter Rate Limits
- **Issue**: Free models on OpenRouter have rate limits (RPM/RPD). Under heavy use or long conversations, requests may fail with 429 errors.
- **Workaround**: Switch to `LLM_PROVIDER=gemini` in `.env` for production workloads.
- **Status**: By design — OpenRouter is for dev/testing only.

### SQL Execution Timeout
- **Issue**: No explicit timeout on SQL queries. A slow or runaway query (e.g., full table scan on large tables) will block the agent response.
- **Workaround**: Use `LIMIT` clauses in freeform queries. The `get_column_stats` tool uses sampling internally.
- **Status**: Deferred — add `statement_timeout` to DB connection string in future.

### LLM May Occasionally Skip Viz Blocks
- **Issue**: Despite explicit instructions, the LLM may occasionally omit `\`\`\`viz` blocks. After prompt improvements, 4/6 test cases now generate viz (up from 1/6).
- **Workaround**: Ask explicitly for a chart (e.g., "muéstrame un gráfico de barras").
- **Status**: Mostly resolved in #20 — added dedicated format instructions for distribution (bar_chart) and temporal (line_chart) queries. Remaining edge cases depend on LLM compliance.
- **Discovered**: #20

## Resolved Issues

### Param Parser Broke SQL with Commas (#20)
- **Issue**: The PARAMS parser in `agent.py` split on commas to separate key=value pairs. This broke any `execute_query` call where the SQL contained commas (e.g., `SELECT col1, col2 FROM ...`).
- **Fix**: Added special handling for `query=` params — takes entire string after `query=` without splitting on commas.
- **Resolved**: #20

### Decision Prompt Lacked SQL Examples (#20)
- **Issue**: The LLM generated incomplete SQL (e.g., `SELECT col` without FROM) because the decision prompt had no examples for `execute_query`.
- **Fix**: Added distribution/grouping and temporal evolution strategies with concrete SQL examples to the decision prompt.
- **Resolved**: #20

# Known Issues - Khipu Analytics

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

## Resolved Issues

_(none yet — track resolutions here with reference to the closing GitHub Issue)_

# Teardown Hook
# Executed when the agent shuts down

## Shutdown Sequence

1. **Complete Pending Operations**
   - Finish any in-progress tool calls
   - Wait for active writes to complete

2. **Flush Audit Logs**
   - Ensure all logs are persisted
   - Close audit log file/connection

3. **Cleanup Resources**
   - Close MCP server connections
   - Release any locks

4. **Final Log Entry**
   - Log "Agent stopped gracefully"
   - Include session duration
   - Summarize operations performed

## Emergency Shutdown

If teardown is interrupted:
- Logs are flushed on SIGTERM
- Partial operations are rolled back (if transactional)
- Audit trail is preserved

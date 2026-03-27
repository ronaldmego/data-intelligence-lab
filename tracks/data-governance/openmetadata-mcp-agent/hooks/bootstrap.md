# Bootstrap Hook
# Executed when the agent starts up

## Startup Sequence

1. **Validate Environment**
   - Check GOOGLE_API_KEY is set
   - Verify OPENMETADATA_URL is reachable
   - Validate OPENMETADATA_TOKEN has required permissions

2. **Initialize Audit Log**
   - Create audit log entry: "Agent started"
   - Log environment (non-sensitive only)

3. **Health Check**
   - Test connection to OpenMetadata
   - Verify tool registration
   - Log available tools count

4. **Load Configuration**
   - Read DRY_RUN_MODE setting
   - Initialize compliance mode

## Success Criteria

- All environment variables present
- OpenMetadata API responds with 200
- At least one tool successfully registered

## Failure Handling

If any check fails:
1. Log detailed error
2. Exit with non-zero code
3. Do not start in degraded mode (safety)

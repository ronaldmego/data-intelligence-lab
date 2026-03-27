# AGENTS.md - Framework-Agnostic Fallback Instructions

## Purpose

This file provides fallback instructions for any framework or runtime that needs to execute this agent without full GitAgent tooling support.

## Minimum Viable Execution

If you're reading this without GitAgent CLI:

### Option 1: Direct MCP Server

```bash
cd skills/openmetadata
pip install fastmcp httpx pydantic
python server.py
```

The server will start on the configured port and expose tools via MCP.

### Option 2: Streamlit UI (Legacy)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Access at http://<vps-host>:4004

### Option 3: LangChain Integration

```python
from langchain_community.tools import BaseTool
import httpx

class OpenMetadataTool(BaseTool):
    """Wrap MCP tools for LangChain"""
    
    def _run(self, query: str):
        # Call the MCP server
        response = httpx.post(
            "http://<vps-host>:4004/tools/search_catalog",
            json={"query": query}
        )
        return response.json()
```

## Environment Setup

```bash
export GOOGLE_API_KEY="your-key"
export OPENMETADATA_URL="http://<vps-host>:8585"
export OPENMETADATA_TOKEN="your-jwt-token"
export DRY_RUN_MODE="false"  # Set to "true" for safe testing
```

## Tool Inventory

See `agent.yaml` for complete tool list and `skills/openmetadata/SKILL.md` for detailed documentation.

## Compliance Notes

- This agent enforces segregation of duties per DUTIES.md
- All write operations require confirmation
- Audit logs are maintained for compliance
- When in doubt, enable DRY_RUN_MODE

## Support

- Repository: https://github.com/ronaldmego/openmetadata-mcp-agent
- GitAgent Spec: https://github.com/open-gitagent/gitagent

"""
OpenMetadata Connector for Khipu
Reads schemas, glossaries, and lineage from OpenMetadata API
"""
import httpx
from typing import Optional
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class OpenMetadataConfig(BaseSettings):
    """OpenMetadata connection settings"""
    host: str = "http://localhost:8585"
    api_version: str = "v1"
    jwt_token: Optional[str] = None
    
    model_config = {"env_prefix": "OPENMETADATA_"}


class TableInfo(BaseModel):
    """Table metadata from OpenMetadata"""
    id: str
    name: str
    fullyQualifiedName: str
    description: Optional[str] = None
    columns: list = []
    tags: list = []


class GlossaryTerm(BaseModel):
    """Business glossary term"""
    id: str
    name: str
    displayName: Optional[str] = None
    description: Optional[str] = None
    synonyms: list = []


class OpenMetadataClient:
    """Client for OpenMetadata API"""
    
    def __init__(self, config: Optional[OpenMetadataConfig] = None):
        self.config = config or OpenMetadataConfig()
        self.base_url = f"{self.config.host}/api/{self.config.api_version}"
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.config.jwt_token:
            headers["Authorization"] = f"Bearer {self.config.jwt_token}"
        return headers
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient(headers=self.headers, timeout=30.0)
        return self
    
    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
    
    async def get_tables(self, database: Optional[str] = None, limit: int = 100) -> list[TableInfo]:
        """Get all tables from the catalog"""
        params = {"limit": limit}
        if database:
            params["database"] = database
        
        response = await self._client.get(f"{self.base_url}/tables", params=params)
        response.raise_for_status()
        
        data = response.json()
        return [TableInfo(**table) for table in data.get("data", [])]
    
    async def get_table(self, fqn: str) -> TableInfo:
        """Get a specific table by fully qualified name"""
        response = await self._client.get(
            f"{self.base_url}/tables/name/{fqn}",
            params={"fields": "columns,tags,description"}
        )
        response.raise_for_status()
        return TableInfo(**response.json())
    
    async def get_glossary_terms(self, glossary: Optional[str] = None) -> list[GlossaryTerm]:
        """Get business glossary terms"""
        params = {"limit": 100}
        if glossary:
            params["glossary"] = glossary
        
        response = await self._client.get(f"{self.base_url}/glossaryTerms", params=params)
        response.raise_for_status()
        
        data = response.json()
        return [GlossaryTerm(**term) for term in data.get("data", [])]
    
    async def search(self, query: str, index: str = "table") -> list:
        """Search across the data catalog"""
        response = await self._client.get(
            f"{self.base_url}/search/query",
            params={"q": query, "index": index}
        )
        response.raise_for_status()
        return response.json().get("hits", {}).get("hits", [])
    
    async def health_check(self) -> bool:
        """Check if OpenMetadata is reachable"""
        try:
            response = await self._client.get(f"{self.config.host}/api/v1/system/version")
            return response.status_code == 200
        except Exception:
            return False


# Convenience function for quick checks
async def test_connection(host: str = "http://localhost:8585") -> dict:
    """Test OpenMetadata connection"""
    config = OpenMetadataConfig(host=host)
    async with OpenMetadataClient(config) as client:
        healthy = await client.health_check()
        tables = await client.get_tables(limit=5) if healthy else []
        return {
            "healthy": healthy,
            "host": host,
            "tables_found": len(tables),
            "sample_tables": [t.name for t in tables[:3]]
        }

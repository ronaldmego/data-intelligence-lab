"""
Khipu Enterprise API
Analytics automation powered by your data catalog
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

from packages.connectors.openmetadata import OpenMetadataClient, OpenMetadataConfig
from packages.core.sql_agent import KhipuSQLAgent

app = FastAPI(
    title="Khipu Enterprise",
    description="Analytics automation powered by OpenMetadata",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config from environment
OM_HOST = os.getenv("OPENMETADATA_HOST", "http://localhost:8585")
OM_TOKEN = os.getenv("OM_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


class ChatRequest(BaseModel):
    question: str
    schema_filter: Optional[str] = "telco_demo"
    execute: bool = False


class ChatResponse(BaseModel):
    question: str
    sql: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None


@app.get("/")
async def root():
    return {
        "name": "Khipu Enterprise",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/catalog")
async def get_catalog(schema: Optional[str] = None, limit: int = 50):
    """Lista tablas del catálogo de OpenMetadata"""
    if not OM_TOKEN:
        raise HTTPException(status_code=500, detail="OM_TOKEN not configured")
    
    config = OpenMetadataConfig(host=OM_HOST, jwt_token=OM_TOKEN)
    async with OpenMetadataClient(config) as client:
        tables = await client.get_tables(limit=limit)
        
        if schema:
            tables = [t for t in tables if schema in t.fullyQualifiedName]
        
        return {
            "tables": [
                {
                    "name": t.name,
                    "fqn": t.fullyQualifiedName,
                    "description": t.description
                }
                for t in tables
            ],
            "count": len(tables)
        }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Convierte pregunta en lenguaje natural a SQL
    
    Ejemplos:
    - "¿Cuántos clientes churned hay?"
    - "¿Cuál es el ARPU del último mes?"
    - "Top 5 ciudades con más clientes"
    """
    if not OM_TOKEN:
        raise HTTPException(status_code=500, detail="OM_TOKEN not configured")
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
    
    # 1. Obtener schema de OpenMetadata
    config = OpenMetadataConfig(host=OM_HOST, jwt_token=OM_TOKEN)
    async with OpenMetadataClient(config) as client:
        tables = await client.get_tables(limit=100)
        
        if request.schema_filter:
            tables = [t for t in tables if request.schema_filter in t.fullyQualifiedName]
        
        # Obtener detalles de columnas para cada tabla
        tables_with_cols = []
        for table in tables:
            try:
                details = await client.get_table(table.fullyQualifiedName)
                tables_with_cols.append({
                    "name": details.name,
                    "description": details.description,
                    "columns": details.columns
                })
            except:
                tables_with_cols.append({
                    "name": table.name,
                    "description": table.description,
                    "columns": []
                })
    
    # 2. Generar SQL
    agent = KhipuSQLAgent(openai_api_key=OPENAI_API_KEY)
    result = await agent.generate_sql(
        question=request.question,
        tables=tables_with_cols,
        execute=request.execute
    )
    
    return ChatResponse(
        question=request.question,
        sql=result.get("sql"),
        result=result.get("result"),
        error=result.get("error") or result.get("execution_error")
    )

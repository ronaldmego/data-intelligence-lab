"""
Khipu Enterprise API
Analytics automation powered by your data catalog
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load .env file
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncpg

from packages.connectors.openmetadata import OpenMetadataClient, OpenMetadataConfig
from packages.core.sql_agent import KhipuSQLAgent
from packages.core.auto_eda import AutoEDA, TableProfile
from packages.core.dashboard_generator import DashboardGenerator

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

# PostgreSQL config
PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5434"))
PG_USER = os.getenv("POSTGRES_USER", "postgres")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
PG_DB = os.getenv("POSTGRES_DB", "khipu")


class ChatRequest(BaseModel):
    question: str
    schema_filter: Optional[str] = "telco_demo"
    execute: bool = False


class ChatResponse(BaseModel):
    question: str
    sql: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None


class AnalyzeRequest(BaseModel):
    """Request para análisis EDA completo"""
    schema_name: str = "telco_demo"
    execute_queries: bool = True
    output_format: str = "json"  # json | html
    sample_size: Optional[int] = None  # Para tablas grandes


class AnalyzeResponse(BaseModel):
    """Response del análisis EDA"""
    schema_name: str
    tables_count: int
    tables_analysis: List[Dict[str, Any]]
    summary: Dict[str, Any]
    generated_at: str
    execution_time_ms: int


async def get_pg_connection():
    """Obtiene conexión a PostgreSQL"""
    try:
        conn = await asyncpg.connect(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
            database=PG_DB
        )
        return conn
    except Exception as e:
        print(f"PostgreSQL connection error: {e}")
        return None


async def execute_query(conn, sql: str) -> Dict:
    """Ejecuta una query y retorna resultados"""
    try:
        rows = await conn.fetch(sql)
        if rows:
            columns = list(rows[0].keys())
            data = [dict(row) for row in rows]
            return {"success": True, "columns": columns, "data": data, "row_count": len(data)}
        return {"success": True, "columns": [], "data": [], "row_count": 0}
    except Exception as e:
        return {"success": False, "error": str(e)}


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


@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest):
    """
    Ejecuta Auto-EDA completo para un schema
    
    Analiza todas las tablas del schema especificado, genera estadísticas
    descriptivas y opcionalmente un dashboard HTML interactivo.
    
    Args:
        schema_name: Schema a analizar (default: telco_demo)
        execute_queries: Si True, ejecuta queries contra la DB para stats reales
        output_format: "json" o "html" 
        sample_size: Límite de filas para tablas grandes (None = sin límite)
    
    Returns:
        JSON con análisis o HTML del dashboard
    """
    start_time = datetime.now()
    
    if not OM_TOKEN:
        raise HTTPException(status_code=500, detail="OM_TOKEN not configured")
    
    # 1. Obtener tablas de OpenMetadata
    config = OpenMetadataConfig(host=OM_HOST, jwt_token=OM_TOKEN)
    tables_data = []
    
    async with OpenMetadataClient(config) as client:
        tables = await client.get_tables(limit=100)
        
        # Filtrar por schema
        tables = [t for t in tables if request.schema_name in t.fullyQualifiedName]
        
        if not tables:
            raise HTTPException(
                status_code=404, 
                detail=f"No tables found in schema: {request.schema_name}"
            )
        
        # Obtener detalles de cada tabla
        for table in tables:
            try:
                details = await client.get_table(table.fullyQualifiedName)
                tables_data.append({
                    "name": details.name,
                    "fullyQualifiedName": details.fullyQualifiedName,
                    "description": details.description,
                    "columns": details.columns,
                    "tags": details.tags
                })
            except Exception as e:
                print(f"Error getting table {table.name}: {e}")
    
    # 2. Ejecutar Auto-EDA
    eda = AutoEDA()
    tables_analysis = []
    
    # Conexión a PostgreSQL si execute_queries=True
    pg_conn = None
    if request.execute_queries:
        pg_conn = await get_pg_connection()
    
    for table_data in tables_data:
        table_name = table_data['name']
        columns = table_data.get('columns', [])
        
        # Crear perfil base
        profile = eda.build_profile_from_openmetadata({
            **table_data,
            'database': {'name': request.schema_name}
        })
        
        # Generar propuesta de análisis
        proposal = eda.create_analysis_proposal(profile)
        
        # Estadísticas de la tabla
        table_stats = {
            'column_count': len(columns),
            'row_count': 0,
            'size_category': profile.size_category,
            'null_percent_avg': 0
        }
        
        # Si tenemos conexión, ejecutar queries para obtener stats reales
        columns_with_stats = []
        
        if pg_conn and columns:
            # Query de conteo
            count_result = await execute_query(
                pg_conn, 
                f"SELECT COUNT(*) as cnt FROM {request.schema_name}.{table_name}"
            )
            if count_result['success'] and count_result['data']:
                table_stats['row_count'] = count_result['data'][0]['cnt']
            
            # Stats por columna
            for col in columns:
                col_name = col.get('name')
                col_type = eda.infer_column_type(col.get('dataType', 'VARCHAR'))
                viz = eda.suggest_visualization(col_type, 0, table_stats['row_count'])
                
                col_stats = {
                    'name': col_name,
                    'sql_type': col.get('dataType'),
                    'inferred_type': col_type.value,
                    'suggested_viz': viz,
                    'stats': {}
                }
                
                # Query de estadísticas básicas
                try:
                    basic_sql = f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT({col_name}) as non_null,
                        COUNT(*) - COUNT({col_name}) as nulls,
                        COUNT(DISTINCT {col_name}) as distinct_count
                    FROM {request.schema_name}.{table_name}
                    """
                    basic_result = await execute_query(pg_conn, basic_sql)
                    
                    if basic_result['success'] and basic_result['data']:
                        data = basic_result['data'][0]
                        total = data['total'] or 1
                        col_stats['stats'] = {
                            'total': data['total'],
                            'non_null': data['non_null'],
                            'nulls': data['nulls'],
                            'distinct': data['distinct_count'],
                            'null_percent': (data['nulls'] / total) * 100 if total else 0
                        }
                    
                    # Stats adicionales para numéricas
                    if col_type.value == 'numeric':
                        num_sql = f"""
                        SELECT 
                            MIN({col_name})::numeric as min_val,
                            MAX({col_name})::numeric as max_val,
                            AVG({col_name})::numeric(12,2) as avg_val,
                            STDDEV({col_name})::numeric(12,2) as std_val
                        FROM {request.schema_name}.{table_name}
                        WHERE {col_name} IS NOT NULL
                        """
                        num_result = await execute_query(pg_conn, num_sql)
                        if num_result['success'] and num_result['data']:
                            num_data = num_result['data'][0]
                            col_stats['stats'].update({
                                'min': float(num_data['min_val']) if num_data['min_val'] else None,
                                'max': float(num_data['max_val']) if num_data['max_val'] else None,
                                'avg': float(num_data['avg_val']) if num_data['avg_val'] else None,
                                'std': float(num_data['std_val']) if num_data['std_val'] else None
                            })
                    
                    # Top valores para categóricas
                    if col_type.value == 'categorical' and col_stats['stats'].get('distinct', 0) <= 50:
                        freq_sql = f"""
                        SELECT {col_name} as value, COUNT(*) as frequency
                        FROM {request.schema_name}.{table_name}
                        WHERE {col_name} IS NOT NULL
                        GROUP BY {col_name}
                        ORDER BY frequency DESC
                        LIMIT 10
                        """
                        freq_result = await execute_query(pg_conn, freq_sql)
                        if freq_result['success']:
                            col_stats['stats']['distribution'] = [
                                {'label': str(r['value']), 'count': r['frequency']}
                                for r in freq_result['data']
                            ]
                
                except Exception as e:
                    col_stats['stats']['error'] = str(e)
                
                columns_with_stats.append(col_stats)
            
            # Calcular promedio de nulos
            if columns_with_stats:
                null_percents = [
                    c['stats'].get('null_percent', 0) 
                    for c in columns_with_stats 
                    if 'null_percent' in c.get('stats', {})
                ]
                if null_percents:
                    table_stats['null_percent_avg'] = sum(null_percents) / len(null_percents)
        
        else:
            # Sin conexión, solo metadata
            columns_with_stats = proposal['columns_analysis']
        
        tables_analysis.append({
            'table': table_name,
            'description': table_data.get('description', ''),
            'statistics': table_stats,
            'columns_analysis': columns_with_stats,
            'suggested_analyses': proposal['suggested_analyses'],
            'warnings': proposal['warnings']
        })
    
    # Cerrar conexión
    if pg_conn:
        await pg_conn.close()
    
    # 3. Calcular resumen
    execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
    
    summary = {
        'total_tables': len(tables_analysis),
        'total_columns': sum(t['statistics']['column_count'] for t in tables_analysis),
        'total_rows': sum(t['statistics']['row_count'] for t in tables_analysis),
        'executed_queries': request.execute_queries
    }
    
    # 4. Generar respuesta
    if request.output_format == 'html':
        generator = DashboardGenerator()
        html = generator.generate_html(
            schema_name=request.schema_name,
            tables_analysis=tables_analysis,
            summary=summary,
            generated_at=datetime.now().isoformat()
        )
        return HTMLResponse(content=html)
    
    return {
        'schema_name': request.schema_name,
        'tables_count': len(tables_analysis),
        'tables_analysis': tables_analysis,
        'summary': summary,
        'generated_at': datetime.now().isoformat(),
        'execution_time_ms': execution_time
    }


@app.get("/api/analyze/{schema_name}/dashboard")
async def get_dashboard(schema_name: str = "telco_demo"):
    """
    Genera dashboard HTML del Auto-EDA
    
    Shortcut para: POST /api/analyze con output_format=html
    """
    request = AnalyzeRequest(
        schema_name=schema_name,
        execute_queries=True,
        output_format="html"
    )
    return await analyze(request)

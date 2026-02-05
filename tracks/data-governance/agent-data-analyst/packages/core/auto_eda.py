"""
Khipu Auto-EDA
Análisis exploratorio automático con inteligencia de volumetría
"""
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
import json

class ColumnType(Enum):
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    DATETIME = "datetime"
    TEXT = "text"
    BOOLEAN = "boolean"
    UNKNOWN = "unknown"


@dataclass
class TableProfile:
    """Perfil de una tabla con metadata de OpenMetadata"""
    name: str
    schema: str
    row_count: Optional[int] = None
    column_count: int = 0
    columns: List[Dict] = None
    size_category: str = "unknown"  # small, medium, large, huge
    estimated_analysis_time: str = "unknown"
    
    def __post_init__(self):
        if self.columns is None:
            self.columns = []
        self._classify_size()
    
    def _classify_size(self):
        """Clasifica el tamaño de la tabla para estimar tiempos"""
        if self.row_count is None:
            self.size_category = "unknown"
            self.estimated_analysis_time = "desconocido"
        elif self.row_count < 1000:
            self.size_category = "small"
            self.estimated_analysis_time = "< 5 segundos"
        elif self.row_count < 100000:
            self.size_category = "medium"
            self.estimated_analysis_time = "10-30 segundos"
        elif self.row_count < 1000000:
            self.size_category = "large"
            self.estimated_analysis_time = "1-5 minutos"
        else:
            self.size_category = "huge"
            self.estimated_analysis_time = "5+ minutos (se recomienda sampling)"


@dataclass
class ColumnAnalysis:
    """Análisis de una columna"""
    name: str
    data_type: str
    inferred_type: ColumnType
    total_count: int = 0
    null_count: int = 0
    null_percent: float = 0.0
    distinct_count: int = 0
    distinct_percent: float = 0.0
    # Para numéricas
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean_value: Optional[float] = None
    std_value: Optional[float] = None
    # Para categóricas
    top_values: List[Dict] = None
    # Visualización sugerida
    suggested_viz: str = "none"
    
    def __post_init__(self):
        if self.top_values is None:
            self.top_values = []


class AutoEDA:
    """Motor de análisis exploratorio automático"""
    
    # Mapeo de tipos SQL a tipos de análisis
    TYPE_MAPPING = {
        'INT': ColumnType.NUMERIC,
        'INTEGER': ColumnType.NUMERIC,
        'BIGINT': ColumnType.NUMERIC,
        'SMALLINT': ColumnType.NUMERIC,
        'DECIMAL': ColumnType.NUMERIC,
        'NUMERIC': ColumnType.NUMERIC,
        'FLOAT': ColumnType.NUMERIC,
        'DOUBLE': ColumnType.NUMERIC,
        'REAL': ColumnType.NUMERIC,
        'VARCHAR': ColumnType.CATEGORICAL,
        'CHAR': ColumnType.CATEGORICAL,
        'TEXT': ColumnType.TEXT,
        'DATE': ColumnType.DATETIME,
        'TIMESTAMP': ColumnType.DATETIME,
        'DATETIME': ColumnType.DATETIME,
        'TIME': ColumnType.DATETIME,
        'BOOLEAN': ColumnType.BOOLEAN,
        'BOOL': ColumnType.BOOLEAN,
    }
    
    def __init__(self, db_connection=None):
        self.db = db_connection
    
    def infer_column_type(self, sql_type: str) -> ColumnType:
        """Infiere el tipo de análisis basado en el tipo SQL"""
        sql_type_upper = sql_type.upper().split('(')[0].strip()
        return self.TYPE_MAPPING.get(sql_type_upper, ColumnType.UNKNOWN)
    
    def suggest_visualization(self, col_type: ColumnType, distinct_count: int, total_count: int) -> str:
        """Sugiere visualización basada en el tipo y cardinalidad"""
        if col_type == ColumnType.NUMERIC:
            return "histogram"
        elif col_type == ColumnType.CATEGORICAL:
            if distinct_count <= 10:
                return "bar_chart"
            elif distinct_count <= 30:
                return "horizontal_bar"
            else:
                return "top_n_bar"  # Solo mostrar top N
        elif col_type == ColumnType.DATETIME:
            return "time_series"
        elif col_type == ColumnType.BOOLEAN:
            return "pie_chart"
        else:
            return "table"
    
    def build_profile_from_openmetadata(self, table_data: Dict) -> TableProfile:
        """Construye perfil desde datos de OpenMetadata"""
        columns = table_data.get('columns', [])
        
        # Intentar obtener row count del profiler de OpenMetadata si existe
        row_count = None
        profile = table_data.get('profile', {})
        if profile:
            row_count = profile.get('rowCount')
        
        return TableProfile(
            name=table_data.get('name', 'unknown'),
            schema=table_data.get('database', {}).get('name', 'unknown'),
            row_count=row_count,
            column_count=len(columns),
            columns=columns
        )
    
    def generate_analysis_sql(self, schema_name: str, table_name: str, columns: List[Dict], sample_size: Optional[int] = None) -> str:
        """Genera SQL para análisis descriptivo"""
        schema_table = f"{schema_name}.{table_name}"
        
        select_parts = []
        for col in columns:
            col_name = col.get('name')
            col_type = self.infer_column_type(col.get('dataType', 'VARCHAR'))
            
            # Estadísticas básicas para todas
            select_parts.append(f"COUNT({col_name}) as {col_name}_count")
            select_parts.append(f"COUNT(*) - COUNT({col_name}) as {col_name}_nulls")
            select_parts.append(f"COUNT(DISTINCT {col_name}) as {col_name}_distinct")
            
            # Estadísticas numéricas
            if col_type == ColumnType.NUMERIC:
                select_parts.append(f"MIN({col_name}) as {col_name}_min")
                select_parts.append(f"MAX({col_name}) as {col_name}_max")
                select_parts.append(f"AVG({col_name})::numeric(10,2) as {col_name}_avg")
                select_parts.append(f"STDDEV({col_name})::numeric(10,2) as {col_name}_std")
        
        sql = f"SELECT\n  " + ",\n  ".join(select_parts) + f"\nFROM {schema_table}"
        
        if sample_size:
            sql += f"\nORDER BY RANDOM() LIMIT {sample_size}"
        
        return sql
    
    def generate_frequency_sql(self, schema_name: str, table_name: str, column_name: str, limit: int = 10) -> str:
        """Genera SQL para frecuencias de valores"""
        return f"""
SELECT {column_name}, COUNT(*) as frequency, 
       ROUND(COUNT(*)::numeric * 100 / SUM(COUNT(*)) OVER(), 2) as percentage
FROM {schema_name}.{table_name}
WHERE {column_name} IS NOT NULL
GROUP BY {column_name}
ORDER BY frequency DESC
LIMIT {limit}
"""
    
    def generate_time_series_sql(self, schema_name: str, table_name: str, date_column: str, value_column: str = None, granularity: str = 'day') -> str:
        """Genera SQL para análisis de series de tiempo"""
        if granularity == 'day':
            date_trunc = f"DATE({date_column})"
        elif granularity == 'week':
            date_trunc = f"DATE_TRUNC('week', {date_column})"
        elif granularity == 'month':
            date_trunc = f"DATE_TRUNC('month', {date_column})"
        else:
            date_trunc = f"DATE({date_column})"
        
        if value_column:
            return f"""
SELECT {date_trunc} as period, 
       COUNT(*) as records,
       SUM({value_column}) as total,
       AVG({value_column})::numeric(10,2) as average
FROM {schema_name}.{table_name}
GROUP BY {date_trunc}
ORDER BY period
"""
        else:
            return f"""
SELECT {date_trunc} as period, COUNT(*) as records
FROM {schema_name}.{table_name}
GROUP BY {date_trunc}
ORDER BY period
"""

    def create_analysis_proposal(self, profile: TableProfile) -> Dict:
        """Crea propuesta de análisis basada en el perfil"""
        proposal = {
            "table": profile.name,
            "schema": profile.schema,
            "summary": {
                "row_count": profile.row_count,
                "column_count": profile.column_count,
                "size_category": profile.size_category,
                "estimated_time": profile.estimated_analysis_time
            },
            "columns_analysis": [],
            "suggested_analyses": [],
            "warnings": []
        }
        
        # Analizar cada columna
        for col in profile.columns:
            col_type = self.infer_column_type(col.get('dataType', 'VARCHAR'))
            analysis = {
                "name": col.get('name'),
                "sql_type": col.get('dataType'),
                "inferred_type": col_type.value,
                "suggested_viz": self.suggest_visualization(col_type, 0, profile.row_count or 0)
            }
            proposal["columns_analysis"].append(analysis)
        
        # Sugerir análisis específicos
        numeric_cols = [c for c in proposal["columns_analysis"] if c["inferred_type"] == "numeric"]
        categorical_cols = [c for c in proposal["columns_analysis"] if c["inferred_type"] == "categorical"]
        datetime_cols = [c for c in proposal["columns_analysis"] if c["inferred_type"] == "datetime"]
        
        if numeric_cols:
            proposal["suggested_analyses"].append({
                "type": "distribution",
                "description": f"Análisis de distribución para {len(numeric_cols)} columnas numéricas",
                "columns": [c["name"] for c in numeric_cols]
            })
        
        if categorical_cols:
            proposal["suggested_analyses"].append({
                "type": "frequency",
                "description": f"Análisis de frecuencias para {len(categorical_cols)} columnas categóricas",
                "columns": [c["name"] for c in categorical_cols]
            })
        
        if datetime_cols:
            proposal["suggested_analyses"].append({
                "type": "time_series",
                "description": f"Análisis temporal para {len(datetime_cols)} columnas de fecha",
                "columns": [c["name"] for c in datetime_cols]
            })
        
        # Warnings
        if profile.size_category == "huge":
            proposal["warnings"].append("Tabla muy grande. Se recomienda usar sampling para el análisis.")
        
        if profile.row_count is None:
            proposal["warnings"].append("No se pudo determinar el tamaño de la tabla. Ejecutar profiler de OpenMetadata primero.")
        
        return proposal
    
    def generate_dashboard_spec(self, schema_name: str, table_name: str, columns: List[Dict]) -> Dict:
        """Genera especificación de dashboard automático"""
        dashboard = {
            "title": f"Auto-EDA: {schema_name}.{table_name}",
            "generated_by": "Khipu",
            "panels": []
        }
        
        for col in columns:
            col_name = col.get('name')
            col_type = self.infer_column_type(col.get('dataType', 'VARCHAR'))
            viz = self.suggest_visualization(col_type, 0, 0)
            
            panel = {
                "title": f"Análisis: {col_name}",
                "column": col_name,
                "type": viz,
                "sql": None
            }
            
            if viz == "histogram":
                panel["sql"] = f"""
SELECT 
  WIDTH_BUCKET({col_name}, 
    (SELECT MIN({col_name}) FROM {schema_name}.{table_name}),
    (SELECT MAX({col_name}) FROM {schema_name}.{table_name}),
    10) as bucket,
  COUNT(*) as frequency
FROM {schema_name}.{table_name}
WHERE {col_name} IS NOT NULL
GROUP BY bucket
ORDER BY bucket
"""
            elif viz in ["bar_chart", "horizontal_bar", "top_n_bar"]:
                panel["sql"] = self.generate_frequency_sql(schema_name, table_name, col_name)
            elif viz == "time_series":
                panel["sql"] = self.generate_time_series_sql(schema_name, table_name, col_name)
            
            dashboard["panels"].append(panel)
        
        return dashboard

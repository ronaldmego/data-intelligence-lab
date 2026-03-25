#!/usr/bin/env python3
"""
DataGov Analyst - Variable Type Classifier
Clasifica columnas según su tipo estadístico para guiar análisis y visualización.

Árbol de decisión basado en data-to-viz.com:
- Numérica continua  → histogram, density, boxplot
- Numérica discreta  → bar chart, histogram
- Categórica         → bar chart, treemap, pie
- Temporal           → line chart, area chart
- Booleana           → bar chart (2 barras)
- Ordinal            → bar chart ordenado
- Texto libre        → wordcloud, tabla (alta cardinalidad)
"""

from dataclasses import dataclass
from typing import Optional


# Tipos SQL que se consideran numéricos
NUMERIC_TYPES = {
    "integer", "bigint", "smallint", "int", "int2", "int4", "int8",
    "numeric", "decimal", "real", "float", "float4", "float8",
    "double precision", "money",
}

# Tipos SQL que se consideran temporales
TEMPORAL_TYPES = {
    "date", "timestamp", "timestamptz", "timestamp without time zone",
    "timestamp with time zone", "time", "timetz", "interval",
}

# Umbral de cardinalidad para distinguir categórica vs texto libre
CATEGORICAL_CARDINALITY_MAX = 50

# Umbral para numérica discreta: si tiene pocos valores únicos relativos al total
DISCRETE_UNIQUE_RATIO = 0.05
DISCRETE_MAX_UNIQUE = 20


@dataclass
class ColumnClassification:
    """Resultado de clasificar una columna."""
    column_name: str
    sql_type: str
    variable_type: str          # numérica_continua, numérica_discreta, categórica, temporal, booleana, ordinal, texto_libre
    recommended_chart: str      # histogram, bar_chart, line_chart, etc.
    recommended_stats: str      # descripción de qué estadísticas aplicar
    cardinality: int
    total_rows: int
    null_pct: float
    notes: str = ""             # observaciones adicionales

    @property
    def cardinality_ratio(self) -> float:
        return self.cardinality / self.total_rows if self.total_rows > 0 else 0

    def to_prompt_text(self) -> str:
        """Representación para incluir en el prompt del agente."""
        return (
            f"{self.column_name} ({self.sql_type}): "
            f"tipo={self.variable_type}, "
            f"únicos={self.cardinality:,}, "
            f"nulls={self.null_pct:.1f}%, "
            f"gráfico={self.recommended_chart}"
            + (f" — {self.notes}" if self.notes else "")
        )


def classify_column(
    column_name: str,
    sql_type: str,
    cardinality: int,
    total_rows: int,
    null_pct: float,
    sample_values: Optional[list] = None,
) -> ColumnClassification:
    """
    Clasificar el tipo estadístico de una columna.

    Args:
        column_name: Nombre de la columna
        sql_type: Tipo SQL (integer, text, timestamp, etc.)
        cardinality: Número de valores únicos
        total_rows: Total de filas en la tabla
        null_pct: Porcentaje de nulos (0-100)
        sample_values: Muestra de valores para desambiguar casos límite

    Returns:
        ColumnClassification con tipo, gráfico recomendado y stats sugeridas
    """
    sql_type_lower = sql_type.lower().strip()
    col_lower = column_name.lower()
    notes = []

    # --- BOOLEANA ---
    if sql_type_lower == "boolean":
        return ColumnClassification(
            column_name=column_name,
            sql_type=sql_type,
            variable_type="booleana",
            recommended_chart="bar_chart",
            recommended_stats="frecuencias de True/False y porcentaje de cada valor",
            cardinality=cardinality,
            total_rows=total_rows,
            null_pct=null_pct,
        )

    # Detectar booleana por valores de muestra (0/1, Y/N, yes/no, true/false)
    if sample_values and cardinality <= 2:
        bool_values = {str(v).lower() for v in sample_values if v is not None}
        if bool_values <= {"0", "1"} or bool_values <= {"y", "n"} or bool_values <= {"yes", "no"} or bool_values <= {"true", "false"}:
            return ColumnClassification(
                column_name=column_name,
                sql_type=sql_type,
                variable_type="booleana",
                recommended_chart="bar_chart",
                recommended_stats="frecuencias de cada valor binario y porcentaje",
                cardinality=cardinality,
                total_rows=total_rows,
                null_pct=null_pct,
                notes="valores binarios detectados por muestra",
            )

    # --- TEMPORAL ---
    if sql_type_lower in TEMPORAL_TYPES:
        return ColumnClassification(
            column_name=column_name,
            sql_type=sql_type,
            variable_type="temporal",
            recommended_chart="line_chart",
            recommended_stats="rango de fechas (min/max), distribución por mes/año, gaps temporales",
            cardinality=cardinality,
            total_rows=total_rows,
            null_pct=null_pct,
        )

    # Detectar temporal por nombre de columna
    temporal_keywords = {"date", "fecha", "time", "timestamp", "created", "updated", "at", "year", "month"}
    if any(kw in col_lower for kw in temporal_keywords) and sql_type_lower in ("text", "varchar", "character varying"):
        notes.append("posible fecha almacenada como texto")

    # --- NUMÉRICA ---
    if sql_type_lower in NUMERIC_TYPES:
        cardinality_ratio = cardinality / total_rows if total_rows > 0 else 0

        # ID o casi único → texto informativo, no graficar
        if cardinality_ratio > 0.95 and cardinality > 100:
            return ColumnClassification(
                column_name=column_name,
                sql_type=sql_type,
                variable_type="identificador",
                recommended_chart="ninguno",
                recommended_stats="verificar unicidad (es posible PK o FK)",
                cardinality=cardinality,
                total_rows=total_rows,
                null_pct=null_pct,
                notes="alta cardinalidad — probable ID o clave",
            )

        # Numérica discreta: pocos valores únicos
        is_discrete = (
            cardinality <= DISCRETE_MAX_UNIQUE or
            cardinality_ratio <= DISCRETE_UNIQUE_RATIO
        )
        if is_discrete:
            return ColumnClassification(
                column_name=column_name,
                sql_type=sql_type,
                variable_type="numérica_discreta",
                recommended_chart="bar_chart",
                recommended_stats="frecuencias por valor, min, max, moda",
                cardinality=cardinality,
                total_rows=total_rows,
                null_pct=null_pct,
            )

        # Numérica continua
        return ColumnClassification(
            column_name=column_name,
            sql_type=sql_type,
            variable_type="numérica_continua",
            recommended_chart="histogram",
            recommended_stats="min, max, media, mediana, std, percentiles (P25/P75/P90), outliers (IQR)",
            cardinality=cardinality,
            total_rows=total_rows,
            null_pct=null_pct,
        )

    # --- CATEGÓRICA / TEXTO ---
    # Para tipos texto: decidir por cardinalidad
    if cardinality == 0:
        return ColumnClassification(
            column_name=column_name,
            sql_type=sql_type,
            variable_type="vacía",
            recommended_chart="ninguno",
            recommended_stats="columna sin valores — revisar calidad",
            cardinality=cardinality,
            total_rows=total_rows,
            null_pct=null_pct,
            notes="columna 100% nula o sin datos",
        )

    if cardinality == 1:
        return ColumnClassification(
            column_name=column_name,
            sql_type=sql_type,
            variable_type="constante",
            recommended_chart="ninguno",
            recommended_stats="columna con un solo valor — posible problema de calidad",
            cardinality=cardinality,
            total_rows=total_rows,
            null_pct=null_pct,
            notes="valor único en toda la columna",
        )

    if cardinality <= CATEGORICAL_CARDINALITY_MAX:
        return ColumnClassification(
            column_name=column_name,
            sql_type=sql_type,
            variable_type="categórica",
            recommended_chart="bar_chart",
            recommended_stats="frecuencias por categoría, moda, top-3 valores, % concentración",
            cardinality=cardinality,
            total_rows=total_rows,
            null_pct=null_pct,
        )

    # Texto libre: alta cardinalidad
    return ColumnClassification(
        column_name=column_name,
        sql_type=sql_type,
        variable_type="texto_libre",
        recommended_chart="tabla",
        recommended_stats="longitud promedio, valores más frecuentes (si los hay)",
        cardinality=cardinality,
        total_rows=total_rows,
        null_pct=null_pct,
        notes=f"alta cardinalidad ({cardinality:,} únicos) — probable texto libre o ID",
    )


def classify_table(columns_info: list[dict]) -> list[ColumnClassification]:
    """
    Clasificar todas las columnas de una tabla.

    Args:
        columns_info: Lista de dicts con keys:
            column_name, sql_type, cardinality, total_rows, null_pct
            (sample_values es opcional)

    Returns:
        Lista de ColumnClassification, una por columna
    """
    return [
        classify_column(
            column_name=col["column_name"],
            sql_type=col["sql_type"],
            cardinality=col["cardinality"],
            total_rows=col["total_rows"],
            null_pct=col["null_pct"],
            sample_values=col.get("sample_values"),
        )
        for col in columns_info
    ]


def classifications_to_prompt(classifications: list[ColumnClassification]) -> str:
    """
    Convertir clasificaciones a texto para incluir en el prompt del agente.
    """
    lines = ["Clasificación de variables:"]
    for c in classifications:
        lines.append(f"  • {c.to_prompt_text()}")
    return "\n".join(lines)

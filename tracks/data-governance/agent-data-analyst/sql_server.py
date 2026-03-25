#!/usr/bin/env python3
"""
SQL MCP Server for DataGov Analyst
Ejecuta queries READ-ONLY contra PostgreSQL/Supabase.

Seguridad: Solo permite SELECT. Bloquea INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from fastmcp import FastMCP
import psycopg2
import psycopg2.extras
import psycopg2.errors

# Cargar .env
load_dotenv(Path(__file__).parent / ".env")

# Configuración PostgreSQL
DB_HOST = os.getenv("SUPABASE_DB_HOST", "localhost")
DB_PORT = int(os.getenv("SUPABASE_DB_PORT", "5433"))
DB_USER = os.getenv("SUPABASE_DB_USER", "postgres")
DB_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD", "")
DB_NAME = os.getenv("SUPABASE_DB_NAME", "postgres")

# Crear servidor MCP
sql_mcp = FastMCP("SQL-Analytics")

# Palabras prohibidas (seguridad)
BLOCKED_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "CREATE", "GRANT", "REVOKE", "EXECUTE", "COPY", "VACUUM"
]


def get_connection():
    """Obtener conexión a PostgreSQL"""
    try:
        return psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname=DB_NAME,
            connect_timeout=10
        )
    except psycopg2.OperationalError as e:
        msg = str(e).strip()
        if "could not connect" in msg or "Connection refused" in msg:
            raise ConnectionError(f"No se pudo conectar a PostgreSQL en {DB_HOST}:{DB_PORT} — ¿está corriendo el servidor?")
        elif "password authentication" in msg:
            raise ConnectionError("Credenciales incorrectas para PostgreSQL (usuario/contraseña)")
        elif "database" in msg and "does not exist" in msg:
            raise ConnectionError(f"La base de datos '{DB_NAME}' no existe")
        else:
            raise ConnectionError(f"Error de conexión a PostgreSQL: {msg}")


def is_safe_query(sql: str) -> bool:
    """Verificar que la query sea solo lectura"""
    sql_upper = sql.upper().strip()
    for keyword in BLOCKED_KEYWORDS:
        # Check if keyword appears as a standalone word
        if keyword in sql_upper.split():
            return False
    return True


def format_results(columns: list, rows: list, max_rows: int = 50) -> str:
    """Formatear resultados como tabla legible"""
    if not rows:
        return "Sin resultados"

    # Truncar si hay muchas filas
    truncated = len(rows) > max_rows
    display_rows = rows[:max_rows]

    # Calcular anchos
    col_widths = [len(str(c)) for c in columns]
    for row in display_rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)[:50]))

    # Header
    header = " | ".join(str(c).ljust(col_widths[i]) for i, c in enumerate(columns))
    separator = "-+-".join("-" * w for w in col_widths)

    # Rows
    lines = [header, separator]
    for row in display_rows:
        line = " | ".join(str(v)[:50].ljust(col_widths[i]) for i, v in enumerate(row))
        lines.append(line)

    if truncated:
        lines.append(f"\n... ({len(rows)} filas totales, mostrando {max_rows})")

    return "\n".join(lines)


@sql_mcp.tool
def execute_query(query: str) -> str:
    """Ejecutar una query SQL de solo lectura contra la base de datos.

    IMPORTANTE: Solo se permiten queries SELECT. Cualquier operación de
    escritura será bloqueada por seguridad.

    Args:
        query: Query SQL a ejecutar (solo SELECT)

    Returns:
        Resultados de la query en formato tabla
    """
    sql = query
    if not is_safe_query(sql):
        return "❌ Error: Solo se permiten queries de lectura (SELECT). Operaciones de escritura están bloqueadas."

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql)
        columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchall()
        cur.close()
        conn.close()

        result = format_results(columns, rows)
        return f"✅ {len(rows)} filas retornadas\n\n{result}"
    except ConnectionError as e:
        return f"❌ Error de conexión: {str(e)}"
    except psycopg2.errors.UndefinedTable as e:
        return f"❌ Tabla no encontrada: {str(e).strip()} — verifica el nombre del schema y tabla"
    except psycopg2.errors.UndefinedColumn as e:
        return f"❌ Columna no encontrada: {str(e).strip()} — verifica el nombre de la columna"
    except psycopg2.errors.SyntaxError as e:
        return f"❌ Error de sintaxis SQL: {str(e).strip()}"
    except Exception as e:
        return f"❌ Error ejecutando query: {str(e)}"


@sql_mcp.tool
def list_schemas() -> str:
    """Listar todos los schemas disponibles en la base de datos.

    Returns:
        Lista de schemas con cantidad de tablas en cada uno
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT schema_name, 
                   (SELECT COUNT(*) FROM information_schema.tables t 
                    WHERE t.table_schema = s.schema_name AND t.table_type = 'BASE TABLE') as table_count
            FROM information_schema.schemata s
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 
                                       'storage', 'vault', 'pgsodium', 'pgsodium_masks',
                                       'extensions', 'graphql', 'graphql_public', 'realtime',
                                       'supabase_functions', 'supabase_migrations', 'auth',
                                       '_realtime', 'net', 'cron', '_analytics',
                                       'pgbouncer')
            AND schema_name NOT LIKE 'pg_temp%%'
            AND schema_name NOT LIKE 'pg_toast%%'
            ORDER BY schema_name
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return "No se encontraron schemas"

        output = ["📂 Schemas disponibles:\n"]
        for schema, count in rows:
            output.append(f"  - {schema} ({count} tablas)")

        return "\n".join(output)
    except Exception as e:
        return f"❌ Error: {str(e)}"


@sql_mcp.tool
def describe_table(schema_name: str, table_name: str) -> str:
    """Obtener estructura detallada de una tabla: columnas, tipos, nullables.

    Args:
        schema_name: Nombre del schema (ej: 'public', 'becgi', 'telco_demo')
        table_name: Nombre de la tabla

    Returns:
        Estructura de la tabla con tipos de datos
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT column_name, data_type, is_nullable, 
                   column_default, character_maximum_length,
                   numeric_precision
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """, (schema_name, table_name))
        columns = cur.fetchall()

        if not columns:
            cur.close()
            conn.close()
            return f"No se encontró la tabla {schema_name}.{table_name}"

        # Row count
        cur.execute(f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}"')
        row_count = cur.fetchone()[0]

        cur.close()
        conn.close()

        output = [
            f"📊 {schema_name}.{table_name}",
            f"   Filas: {row_count:,}",
            f"   Columnas: {len(columns)}",
            ""
        ]

        for col_name, data_type, nullable, default, max_len, precision in columns:
            type_str = data_type
            if max_len:
                type_str += f"({max_len})"
            elif precision:
                type_str += f"({precision})"
            null_str = "NULL" if nullable == "YES" else "NOT NULL"
            output.append(f"  - {col_name}: {type_str} [{null_str}]")

        return "\n".join(output)
    except Exception as e:
        return f"❌ Error: {str(e)}"


@sql_mcp.tool
def get_column_stats(schema_name: str, table_name: str, column_name: str) -> str:
    """Obtener estadísticas descriptivas de una columna específica.

    Para numéricas: min, max, avg, median, stddev, percentiles.
    Para categóricas: valores únicos, top frecuencias, moda.

    Args:
        schema_name: Nombre del schema
        table_name: Nombre de la tabla
        column_name: Nombre de la columna

    Returns:
        Estadísticas descriptivas de la columna
    """
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Primero detectar tipo de dato
        cur.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s AND column_name = %s
        """, (schema_name, table_name, column_name))
        result = cur.fetchone()

        if not result:
            cur.close()
            conn.close()
            return f"No se encontró la columna {column_name} en {schema_name}.{table_name}"

        data_type = result[0]
        fqn = f'"{schema_name}"."{table_name}"'
        col = f'"{column_name}"'

        # Stats básicas (para cualquier tipo)
        cur.execute(f"""
            SELECT 
                COUNT(*) as total,
                COUNT({col}) as non_null,
                COUNT(*) - COUNT({col}) as nulls,
                COUNT(DISTINCT {col}) as distinct_count
            FROM {fqn}
        """)
        basic = cur.fetchone()
        total, non_null, nulls, distinct = basic
        null_pct = (nulls / total * 100) if total > 0 else 0

        output = [
            f"📈 Estadísticas: {schema_name}.{table_name}.{column_name}",
            f"   Tipo: {data_type}",
            f"   Total filas: {total:,}",
            f"   No nulos: {non_null:,}",
            f"   Nulos: {nulls:,} ({null_pct:.1f}%)",
            f"   Valores únicos: {distinct:,}",
            ""
        ]

        # Stats numéricas
        numeric_types = ['integer', 'bigint', 'smallint', 'numeric', 'real',
                         'double precision', 'decimal', 'float']
        if data_type in numeric_types:
            cur.execute(f"""
                SELECT 
                    MIN({col})::numeric as min_val,
                    MAX({col})::numeric as max_val,
                    AVG({col})::numeric(15,2) as avg_val,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {col})::numeric(15,2) as median,
                    STDDEV({col})::numeric(15,2) as std_val,
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {col})::numeric(15,2) as p25,
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {col})::numeric(15,2) as p75
                FROM {fqn}
                WHERE {col} IS NOT NULL
            """)
            stats = cur.fetchone()
            if stats:
                min_v, max_v, avg_v, median, std, p25, p75 = stats
                output.append("   📊 Estadísticas numéricas:")
                output.append(f"   Min: {min_v}")
                output.append(f"   Max: {max_v}")
                output.append(f"   Media: {avg_v}")
                output.append(f"   Mediana: {median}")
                output.append(f"   Desv. estándar: {std}")
                output.append(f"   P25: {p25}")
                output.append(f"   P75: {p75}")
                if p25 and p75:
                    iqr = float(p75) - float(p25)
                    output.append(f"   IQR: {iqr:.2f}")

        # Stats categóricas (top 10 frecuencias)
        else:
            if distinct <= 100:  # Solo si cardinalidad es razonable
                cur.execute(f"""
                    SELECT {col}::text as value, COUNT(*) as frequency
                    FROM {fqn}
                    WHERE {col} IS NOT NULL
                    GROUP BY {col}
                    ORDER BY frequency DESC
                    LIMIT 10
                """)
                freq = cur.fetchall()
                if freq:
                    output.append("   📊 Top valores más frecuentes:")
                    for val, count in freq:
                        pct = (count / non_null * 100) if non_null > 0 else 0
                        output.append(f"   {val}: {count:,} ({pct:.1f}%)")
            else:
                output.append(f"   ⚠️ Alta cardinalidad ({distinct:,} valores únicos) - no se muestran frecuencias")

        cur.close()
        conn.close()

        return "\n".join(output)
    except Exception as e:
        return f"❌ Error: {str(e)}"


@sql_mcp.tool
def get_table_profile(schema_name: str, table_name: str) -> str:
    """Perfil rápido de una tabla: resumen de todas las columnas con stats básicas.

    Args:
        schema_name: Nombre del schema
        table_name: Nombre de la tabla

    Returns:
        Perfil completo de la tabla
    """
    try:
        conn = get_connection()
        cur = conn.cursor()

        fqn = f'"{schema_name}"."{table_name}"'

        # Row count
        cur.execute(f"SELECT COUNT(*) FROM {fqn}")
        row_count = cur.fetchone()[0]

        # Columns info
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """, (schema_name, table_name))
        columns = cur.fetchall()

        if not columns:
            cur.close()
            conn.close()
            return f"No se encontró la tabla {schema_name}.{table_name}"

        output = [
            f"📋 Perfil: {schema_name}.{table_name}",
            f"   Filas: {row_count:,} | Columnas: {len(columns)}",
            ""
        ]

        numeric_types = ['integer', 'bigint', 'smallint', 'numeric', 'real',
                         'double precision', 'decimal', 'float']

        for col_name, data_type, nullable in columns:
            col = f'"{col_name}"'

            # Basic stats
            cur.execute(f"""
                SELECT COUNT({col}) as non_null,
                       COUNT(*) - COUNT({col}) as nulls,
                       COUNT(DISTINCT {col}) as distinct_count
                FROM {fqn}
            """)
            non_null, nulls, distinct = cur.fetchone()
            null_pct = (nulls / row_count * 100) if row_count > 0 else 0

            line = f"  {col_name} ({data_type}): {distinct} únicos, {null_pct:.0f}% nulls"

            # Quick stats for numeric
            if data_type in numeric_types and non_null > 0:
                cur.execute(f"""
                    SELECT MIN({col})::numeric, MAX({col})::numeric, 
                           AVG({col})::numeric(12,2)
                    FROM {fqn} WHERE {col} IS NOT NULL
                """)
                min_v, max_v, avg_v = cur.fetchone()
                line += f" | min={min_v} max={max_v} avg={avg_v}"

            # Quick stats for categorical
            elif data_type not in numeric_types and distinct > 0 and distinct <= 20:
                cur.execute(f"""
                    SELECT {col}::text, COUNT(*) FROM {fqn}
                    WHERE {col} IS NOT NULL
                    GROUP BY {col} ORDER BY COUNT(*) DESC LIMIT 3
                """)
                top = cur.fetchall()
                top_str = ", ".join(f"{v}({c})" for v, c in top)
                line += f" | top: {top_str}"

            output.append(line)

        cur.close()
        conn.close()

        return "\n".join(output)
    except Exception as e:
        return f"❌ Error: {str(e)}"


if __name__ == "__main__":
    print(f"🚀 SQL MCP Server")
    print(f"   Host: {DB_HOST}:{DB_PORT}")
    print(f"   DB: {DB_NAME}")
    sql_mcp.run()

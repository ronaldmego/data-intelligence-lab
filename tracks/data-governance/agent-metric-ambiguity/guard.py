"""Guard de solo lectura — capa 1 de tres.

Las otras dos capas viven en `pg_client.py` y **no** son sustituibles por ésta:

  1. (este módulo) se analiza la sentencia antes de mandarla.
  2. transacción `READ ONLY`: el motor rechaza la escritura aunque la capa 1 falle.
  3. rol sin permisos de escritura: no hay nada que escribir aunque fallen 1 y 2.

Un guard de una sola capa es una promesa, no un control. Las tres juntas son la
diferencia entre "el agente no debería escribir" y "el agente no puede".

**Por qué no una lista negra de palabras.** El proyecto hermano
(`agent-data-analyst/sql_server.py`) enumera lo prohibido y tokeniza con
`split()`, que parte por espacios. `SELECT 1;DROP TABLE store` pasa entero
porque el token es `1;DROP`, que no figura en la lista. Enumerar lo prohibido
obliga a acertarle a todas las formas de escribirlo; enumerar lo permitido
obliga al atacante a caber en ellas. Acá el criterio se invierte: la sentencia
tiene que ser **una sola** y empezar por `SELECT` o `WITH`, con los literales y
comentarios neutralizados antes de mirarla. Lo demás no tiene por dónde entrar.

Sin dependencias de terceros a propósito: la CI del monorepo corre
`uvx pytest`, en un entorno efímero que no instala las dependencias del
proyecto. Todo lo que la CI deba verificar tiene que importarse con la
biblioteca estándar.
"""

from __future__ import annotations

import re

MAX_QUERY_LENGTH = 8_000

#: Una sentencia de lectura sólo puede empezar por una de éstas.
ALLOWED_LEADING = frozenset({"SELECT", "WITH"})

#: Palabras que no pueden aparecer en ninguna posición de una consulta de
#: lectura. No es la defensa principal —lo es `ALLOWED_LEADING` más la regla de
#: sentencia única— sino la red para las formas que sí caben en un `SELECT`:
#:
#: - ``SELECT … INTO nueva FROM …`` crea una tabla y empieza por SELECT.
#: - ``WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x`` es un CTE que
#:   escribe: PostgreSQL admite sentencias de modificación dentro de un `WITH`.
FORBIDDEN_TOKENS = frozenset({
    "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT",
    "DROP", "ALTER", "CREATE", "TRUNCATE", "COMMENT",
    "GRANT", "REVOKE", "SECURITY",
    "COPY", "VACUUM", "REINDEX", "CLUSTER", "REFRESH", "ANALYSE", "ANALYZE",
    "CALL", "DO", "EXECUTE", "PREPARE", "DEALLOCATE",
    "SET", "RESET", "DISCARD", "LOCK",
    "LISTEN", "NOTIFY", "UNLISTEN",
    "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT",
    "INTO",
})

#: Funciones que leen o tocan cosas fuera de las tablas del negocio. Un rol sin
#: grants ya frena a casi todas; `pg_sleep` no escribe nada y aun así deja la
#: conexión colgada, que es por lo que además hay `statement_timeout`.
FORBIDDEN_FUNCTIONS = frozenset({
    "pg_sleep", "pg_sleep_for", "pg_sleep_until",
    "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file",
    "lo_import", "lo_export",
    "dblink", "dblink_exec", "postgres_fdw_handler",
    "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf",
    "query_to_xml", "pg_logical_emit_message",
})

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_DOLLAR_TAG = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")
#: Identificador simple de PostgreSQL sin comillas. Se usa para validar los
#: nombres que llegan **desde el catálogo**, que es entrada no confiable.
_PLAIN_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class UnsafeQuery(ValueError):
    """La consulta no pasó la capa 1. Lleva el motivo en `.reason`."""

    def __init__(self, reason: str, query: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.query = query


def _neutralize(sql: str) -> str:
    """Reemplaza comentarios y literales por marcadores inertes.

    Sin este paso el análisis se puede engañar por los dos lados: un
    ``/**/`` intercalado esconde una palabra prohibida, y un literal
    ``WHERE nota = 'DROP'`` dispara un falso positivo. Se recorre a mano en vez
    de usar expresiones regulares porque los comentarios de bloque de
    PostgreSQL **anidan** y las comillas se escapan duplicándose.

    Una comilla o un comentario sin cerrar levanta `UnsafeQuery`: preferimos
    rechazar una consulta rara antes que analizar un texto que el motor va a
    interpretar de otra forma.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        two = sql[i:i + 2]

        if two == "--":
            j = sql.find("\n", i)
            i = n if j == -1 else j
            out.append(" ")
            continue

        if two == "/*":
            depth, i = 1, i + 2
            while i < n and depth:
                if sql[i:i + 2] == "/*":
                    depth += 1
                    i += 2
                elif sql[i:i + 2] == "*/":
                    depth -= 1
                    i += 2
                else:
                    i += 1
            if depth:
                raise UnsafeQuery("comentario de bloque sin cerrar", sql)
            out.append(" ")
            continue

        ch = sql[i]

        # Cadenas con escapes de barra invertida (E'...'). No hacen falta para
        # una consulta de lectura y cambian las reglas de escapado, así que se
        # rechazan en vez de intentar interpretarlas.
        if ch in "Ee" and sql[i + 1:i + 2] == "'":
            raise UnsafeQuery("cadena con escapes E'...' no admitida", sql)

        if ch == "'":
            i += 1
            closed = False
            while i < n:
                if sql[i] == "'":
                    if sql[i + 1:i + 2] == "'":   # '' es una comilla escapada
                        i += 2
                        continue
                    i += 1
                    closed = True
                    break
                i += 1
            if not closed:
                raise UnsafeQuery("literal de texto sin cerrar", sql)
            out.append(" 'x' ")
            continue

        if ch == '"':
            i += 1
            closed = False
            while i < n:
                if sql[i] == '"':
                    if sql[i + 1:i + 2] == '"':
                        i += 2
                        continue
                    i += 1
                    closed = True
                    break
                i += 1
            if not closed:
                raise UnsafeQuery("identificador entrecomillado sin cerrar", sql)
            out.append(' "x" ')
            continue

        if ch == "$":
            m = _DOLLAR_TAG.match(sql, i)
            if m:
                tag = m.group(0)
                j = sql.find(tag, m.end())
                if j == -1:
                    raise UnsafeQuery("cadena con dólar sin cerrar", sql)
                i = j + len(tag)
                out.append(" 'x' ")
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def check_query(sql: str) -> str:
    """Valida una consulta de lectura y devuelve la versión saneada.

    Levanta `UnsafeQuery` con el motivo si no pasa. Devolver la consulta en vez
    de un booleano es a propósito: obliga a que quien la ejecute haya pasado por
    acá, en lugar de poder consultar el guard y después mandar otra cosa.
    """
    if not isinstance(sql, str):
        raise UnsafeQuery("la consulta debe ser texto")
    if len(sql) > MAX_QUERY_LENGTH:
        raise UnsafeQuery(f"consulta de más de {MAX_QUERY_LENGTH} caracteres")

    neutral = _neutralize(sql)

    stripped = neutral.strip().rstrip(";").strip()
    if not stripped:
        raise UnsafeQuery("consulta vacía", sql)

    # Sentencia única. El `;` final ya se quitó arriba, así que cualquier `;`
    # que quede separa dos sentencias.
    if ";" in stripped:
        raise UnsafeQuery("se admite una sola sentencia por llamada", sql)

    tokens = _WORD.findall(stripped)
    if not tokens:
        raise UnsafeQuery("la consulta no tiene ninguna palabra reconocible", sql)

    leading = tokens[0].upper()
    if leading not in ALLOWED_LEADING:
        raise UnsafeQuery(
            f"una consulta de lectura debe empezar por SELECT o WITH, no por {leading}", sql
        )

    upper = {t.upper() for t in tokens}
    prohibidas = sorted(upper & FORBIDDEN_TOKENS)
    if prohibidas:
        raise UnsafeQuery(f"palabra no admitida en una consulta de lectura: {prohibidas[0]}", sql)

    lower = {t.lower() for t in tokens}
    funciones = sorted(lower & FORBIDDEN_FUNCTIONS)
    if funciones:
        raise UnsafeQuery(f"función no admitida: {funciones[0]}", sql)

    return sql


def is_safe_query(sql: str) -> bool:
    """Variante booleana, para comparar contra guards de otros proyectos."""
    try:
        check_query(sql)
    except UnsafeQuery:
        return False
    return True


def safe_identifier(name: str, *, kind: str = "identificador") -> str:
    """Valida un nombre que viene **del catálogo** antes de interpolarlo en SQL.

    El catálogo es entrada no confiable: sus nombres y descripciones los escribe
    gente, y este POC arma sus consultas a partir de ellos. Un nombre de columna
    como ``store_id from x; drop table y --`` convertiría la derivación desde
    metadata en una inyección. Los identificadores de PostgreSQL no llevan
    parámetros, así que la única defensa es no aceptar ninguno que no tenga
    forma de identificador.
    """
    if not isinstance(name, str) or not _PLAIN_IDENTIFIER.match(name):
        raise UnsafeQuery(f"{kind} inválido proveniente del catálogo: {name!r}")
    return name

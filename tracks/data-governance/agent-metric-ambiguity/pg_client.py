"""Adaptador de PostgreSQL: capas 2 y 3 del control de solo lectura.

La capa 1 (`guard.check_query`) analiza el texto antes de mandarlo. Es
necesaria y no alcanza: cualquier análisis de texto es una carrera contra las
formas de escribir lo mismo. Las dos capas de acá no dependen de haber
anticipado la forma.

* **Capa 2 — transacción de solo lectura.** `set_session(readonly=True)` hace
  que sea el motor el que rechace la escritura. Da igual cómo esté escrita, si
  el guard la entendió o si la generó un modelo: PostgreSQL responde
  *"cannot execute … in a read-only transaction"*.
* **Capa 3 — rol sin permisos.** La conexión usa el rol de práctica, que sólo
  tiene SELECT. Aunque fallaran las dos capas anteriores, no hay privilegio que
  ejercer.

Y un `statement_timeout`, que no es una capa de escritura pero cubre el otro
daño posible desde una consulta de lectura: dejar la conexión colgada.

`verify_read_only()` no confía en nada de lo anterior y lo comprueba contra el
motor. Es la diferencia entre documentar un control y demostrarlo.
"""

from __future__ import annotations

import os

import psycopg2

from guard import check_query

DEFAULT_TIMEOUT_MS = 15_000

#: Sentencias que el motor **tiene** que rechazar. Se mandan salteando la capa
#: 1 a propósito: lo que se está probando es que las capas 2 y 3 aguantan solas.
#: Ninguna escribe nada — todas mueren antes, que es justamente el punto.
_INTENTOS_DE_ESCRITURA = (
    "CREATE TEMP TABLE poc_intento (x int)",
    "DELETE FROM public.store WHERE false",
    "UPDATE public.store SET store_id = store_id WHERE false",
    "INSERT INTO public.store (store_id) SELECT 0 WHERE false",
    "DROP TABLE IF EXISTS public.no_existe",
)


class ReadOnlyPostgres:
    """Implementa `SqlPort`. Devuelve un escalar y nada más."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        dbname: str,
        statement_timeout_ms: int = DEFAULT_TIMEOUT_MS,
        connect_timeout: int = 10,
    ) -> None:
        self._conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=dbname,
            connect_timeout=connect_timeout,
        )
        # Capa 2. `autocommit=False` mantiene todo dentro de una transacción,
        # que es lo que le da sentido a `readonly`.
        self._conn.set_session(readonly=True, autocommit=False)
        with self._conn.cursor() as cur:
            cur.execute("SET statement_timeout = %s", (statement_timeout_ms,))
        self._conn.commit()

    def scalar(self, sql: str) -> int:
        # La capa 1 se vuelve a aplicar acá aunque el orquestador ya la haya
        # aplicado: este objeto puede llamarse desde otro lado —el servidor MCP,
        # por ejemplo— y un control que depende de que el llamador se acuerde no
        # es un control.
        checked = check_query(sql)
        try:
            with self._conn.cursor() as cur:
                cur.execute(checked)
                row = cur.fetchone()
        finally:
            # Nunca dejar una transacción abierta colgando de la conexión.
            self._conn.rollback()
        if row is None or row[0] is None:
            raise ValueError(f"la consulta no devolvió un escalar: {checked}")
        return int(row[0])

    def verify_read_only(self) -> list[tuple[str, str]]:
        """Comprueba contra el motor que la escritura está cerrada.

        Devuelve la lista `(sentencia, resultado)`. Un `PERMITIDA` en cualquier
        fila es un fallo grave del POC, no un detalle.
        """
        out: list[tuple[str, str]] = []
        for sentencia in _INTENTOS_DE_ESCRITURA:
            try:
                with self._conn.cursor() as cur:
                    cur.execute(sentencia)
                out.append((sentencia, "PERMITIDA — el control falló"))
            except psycopg2.Error as exc:
                mensaje = str(exc).strip().splitlines()[0]
                out.append((sentencia, f"rechazada por el motor: {mensaje}"))
            finally:
                self._conn.rollback()
        return out

    def server_version(self) -> str:
        with self._conn.cursor() as cur:
            cur.execute("SELECT version()")
            value = cur.fetchone()[0]
        self._conn.rollback()
        return value.split(",")[0]

    def close(self) -> None:
        self._conn.close()


def from_env() -> ReadOnlyPostgres:
    """Construye la conexión desde el entorno. La credencial no se imprime."""
    missing = [k for k in ("PAGILA_HOST", "PAGILA_USER", "PAGILA_PASSWORD") if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"faltan variables de entorno: {', '.join(missing)}")
    return ReadOnlyPostgres(
        host=os.environ["PAGILA_HOST"],
        port=int(os.getenv("PAGILA_PORT", "5432")),
        user=os.environ["PAGILA_USER"],
        password=os.environ["PAGILA_PASSWORD"],
        dbname=os.getenv("PAGILA_DB", "pagila"),
    )

"""Tests del guard de solo lectura.

Sólo biblioteca estándar, así que la CI los corre con `uvx pytest` sin instalar nada.

Lo que se defiende acá no es "el guard rechaza un DROP" — eso lo hace hasta una
lista de palabras. Se defiende que el guard aguante las formas en que una lista
de palabras se rompe, que son las que dejaron pasar el guard del proyecto
hermano cuando se lo midió:

* la sentencia apilada sin espacio, donde `1;DROP` es un solo token;
* los comentarios de bloque usados como separador;
* `SELECT … INTO`, que crea una tabla y empieza por SELECT;
* los verbos que la lista simplemente no enumeró (MERGE, CALL, DO, REFRESH);
* `pg_sleep`, que no escribe nada y deja la conexión colgada igual.

Y en el otro sentido: que no rechace una consulta legítima por tener la palabra
prohibida dentro de un literal, que es el falso positivo clásico de la lista
negra.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

import pytest  # noqa: E402

from guard import (  # noqa: E402
    UnsafeQuery,
    check_query,
    is_safe_query,
    safe_identifier,
)

#: Las ocho formas que el guard del proyecto hermano deja pasar (medido sobre
#: su función copiada literalmente). Acá tienen que caer todas.
EVASIONES_CONOCIDAS = [
    "SELECT 1;DROP TABLE store",
    "SELECT/**/1;DROP/**/TABLE/**/store",
    "SELECT * INTO nueva FROM store",
    "MERGE INTO store USING x ON true WHEN MATCHED THEN DELETE",
    "CALL algun_proc()",
    "DO $$ BEGIN PERFORM 1; END $$",
    "REFRESH MATERIALIZED VIEW rental_by_category",
    "SELECT pg_sleep(600)",
]

MUTANTES_OBVIOS = [
    "DROP TABLE store",
    "DELETE FROM store",
    "UPDATE store SET store_id = 1",
    "INSERT INTO store VALUES (1, 1, 1)",
    "TRUNCATE store",
    "ALTER TABLE store ADD COLUMN x int",
    "GRANT ALL ON store TO public",
    "CREATE TABLE nueva AS SELECT * FROM store",
    "COPY store TO '/tmp/x.csv'",
]

LECTURAS_LEGITIMAS = [
    "SELECT count(*) AS value FROM public.store",
    "SELECT count(DISTINCT t.store_id) AS value FROM public.customer t",
    "SELECT count(*) FROM (SELECT DISTINCT j.store_id FROM public.payment t "
    "JOIN public.staff j ON j.staff_id = t.staff_id) u",
    "WITH x AS (SELECT store_id FROM public.store) SELECT count(*) FROM x",
    "SELECT count(*) FROM public.store -- cuenta el maestro",
    "SELECT count(*) FROM public.store /* comentario */ WHERE store_id > 0",
    "select 1",
    "SELECT count(*) FROM public.store;",
]


@pytest.mark.parametrize("sql", EVASIONES_CONOCIDAS)
def test_bloquea_las_evasiones_de_la_lista_negra(sql):
    with pytest.raises(UnsafeQuery):
        check_query(sql)


@pytest.mark.parametrize("sql", MUTANTES_OBVIOS)
def test_bloquea_los_mutantes_obvios(sql):
    assert not is_safe_query(sql)


@pytest.mark.parametrize("sql", LECTURAS_LEGITIMAS)
def test_permite_las_lecturas_legitimas(sql):
    assert check_query(sql) == sql


def test_no_confunde_un_literal_con_una_instruccion():
    """El falso positivo clásico: la palabra prohibida es un dato, no un verbo."""
    assert is_safe_query("SELECT * FROM public.nota WHERE texto = 'DROP TABLE store'")
    assert is_safe_query("SELECT 'delete me' AS etiqueta")


def test_una_sola_sentencia_por_llamada():
    with pytest.raises(UnsafeQuery, match="una sola sentencia"):
        check_query("SELECT 1; SELECT 2")


def test_el_punto_y_coma_final_no_molesta():
    assert is_safe_query("SELECT count(*) FROM public.store ;  ")


def test_rechaza_literales_sin_cerrar():
    """Analizar un texto que el motor va a leer distinto es peor que rechazarlo."""
    with pytest.raises(UnsafeQuery, match="sin cerrar"):
        check_query("SELECT * FROM t WHERE x = 'abierto")
    with pytest.raises(UnsafeQuery, match="sin cerrar"):
        check_query("SELECT 1 /* nunca cierro")


def test_rechaza_cadenas_con_escapes_de_barra():
    with pytest.raises(UnsafeQuery, match="E'"):
        check_query(r"SELECT E'\x41'")


def test_comentarios_de_bloque_anidados():
    """PostgreSQL los anida; un parser que no lo sepa cree que ya salió."""
    assert is_safe_query("SELECT 1 /* a /* b */ c */ ")
    with pytest.raises(UnsafeQuery):
        check_query("SELECT 1 /* a /* b */ ; DROP TABLE store")


def test_vacio_y_no_texto():
    with pytest.raises(UnsafeQuery):
        check_query("   ")
    with pytest.raises(UnsafeQuery):
        check_query(None)  # type: ignore[arg-type]


def test_limite_de_longitud():
    with pytest.raises(UnsafeQuery, match="caracteres"):
        check_query("SELECT " + "1," * 5000 + "1")


def test_cte_que_escribe_no_pasa_por_empezar_con_with():
    """`WITH` está permitido, pero un CTE puede modificar datos en PostgreSQL."""
    with pytest.raises(UnsafeQuery):
        check_query("WITH x AS (DELETE FROM store RETURNING *) SELECT * FROM x")


class TestIdentificadoresDelCatalogo:
    """El catálogo es entrada no confiable: sus nombres terminan dentro del SQL.

    Un identificador no se puede pasar como parámetro, así que la única defensa
    es no aceptar ninguno que no tenga forma de identificador.
    """

    def test_acepta_identificadores_normales(self):
        assert safe_identifier("store") == "store"
        assert safe_identifier("store_id") == "store_id"
        assert safe_identifier("_privado") == "_privado"

    @pytest.mark.parametrize(
        "nombre",
        [
            "store; DROP TABLE x",
            "store id",
            'store" OR 1=1 --',
            "Store",          # las mayúsculas cambian el significado sin comillas
            "1store",
            "",
            "público",
            "x" * 70,
        ],
    )
    def test_rechaza_lo_que_no_es_un_identificador(self, nombre):
        with pytest.raises(UnsafeQuery):
            safe_identifier(nombre)

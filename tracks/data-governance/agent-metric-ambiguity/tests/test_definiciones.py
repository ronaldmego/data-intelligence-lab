"""Tests de la derivación de definiciones desde el catálogo.

Sólo biblioteca estándar. El SQL derivado se ejecuta contra un sqlite en
memoria, así que un join mal armado falla acá y no en producción.

La pregunta que estos tests contestan no es "¿da cinco números?" sino **"¿los
da porque los leyó del catálogo o porque están escritos en el código?"**. Un
POC que hardcodee las cinco consultas pasaría cualquier test de valores y sería
una puesta en escena. Por eso la mitad de este archivo mutila el catálogo y
exige que la salida cambie en consecuencia.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

import pytest  # noqa: E402
from fakes import EXPECTED, TABLES, FakeCatalog, FakeSql  # noqa: E402

from definitions import KIND_ACTIVIDAD, KIND_PRESENCIA, KIND_REGISTRO, derive_plan  # noqa: E402
from facts import ColumnFacts, Lineage, TableFacts  # noqa: E402
from guard import UnsafeQuery  # noqa: E402
from orchestrator import run  # noqa: E402

PREGUNTA = "¿Cuántas tiendas tiene el negocio?"


def correr(catalog=None, sql=None):
    catalog = catalog or FakeCatalog()
    sql = sql or FakeSql()
    gov, plan, trace = run(PREGUNTA, catalog, sql, concept="tienda", aliases=("store",))
    return gov, plan, trace


class TestValores:
    def test_las_cinco_definiciones_con_sus_valores(self):
        _, plan, _ = correr()
        assert {c.id: c.value for c in plan.candidates} == EXPECTED

    def test_son_cinco_lecturas_y_cuatro_numeros_distintos(self):
        """El punto del caso: varias fuentes legítimas, varios números."""
        _, plan, _ = correr()
        assert len(plan.candidates) == 5
        assert len({c.value for c in plan.candidates}) == 4

    def test_hay_una_sola_definicion_de_registro_y_una_de_actividad(self):
        _, plan, _ = correr()
        kinds = [c.kind for c in plan.candidates]
        assert kinds.count(KIND_REGISTRO) == 1
        assert kinds.count(KIND_ACTIVIDAD) == 1
        assert kinds.count(KIND_PRESENCIA) == 3

    def test_los_caminos_alternativos_de_actividad_coinciden(self):
        _, plan, _ = correr()
        assert len(plan.corroborations) == 4
        assert {c.value for c in plan.corroborations} == {2}

    def test_cada_definicion_declara_sus_fuentes(self):
        _, plan, _ = correr()
        for c in plan.candidates:
            assert c.sources, f"{c.id} no declara de dónde salió"
            assert all(f.startswith("pagila_source.") for f in c.sources)

    def test_el_sql_derivado_es_ejecutable(self):
        """Si el generador arma un join inválido, sqlite lo rechaza."""
        sql = FakeSql()
        _, plan, _ = correr(sql=sql)
        assert len(sql.executed) == len(plan.candidates) + len(plan.corroborations)


class TestLaDerivacionSigueAlCatalogo:
    """Mutilar el catálogo tiene que cambiar la salida. Si no, está hardcodeado."""

    def test_sin_la_columna_clave_desaparece_esa_definicion(self):
        sin_store_id = TableFacts(
            name="staff",
            fqn=TABLES["staff"].fqn,
            schema="public",
            description="Personal, ahora sin tienda declarada.",
            columns=(ColumnFacts("staff_id"), ColumnFacts("address_id")),
        )

        class Catalogo(FakeCatalog):
            def get_table(self, name):
                return sin_store_id if name == "staff" else super().get_table(name)

        _, plan, _ = correr(catalog=Catalogo())
        ids = {c.id for c in plan.candidates}
        assert "presencia:staff" not in ids
        assert "presencia:customer" in ids, "las demás definiciones no deberían verse afectadas"

    def test_sin_la_arista_de_linaje_desaparece_esa_definicion(self):
        class Catalogo(FakeCatalog):
            def get_lineage(self, table):
                if table.name == "store":
                    return Lineage(downstream=("inventory", "staff"))
                return super().get_lineage(table)

        _, plan, _ = correr(catalog=Catalogo())
        ids = {c.id for c in plan.candidates}
        assert "presencia:customer" not in ids
        assert "presencia:inventory" in ids

    def test_sin_tablas_transaccionales_no_hay_definicion_de_actividad(self):
        class Catalogo(FakeCatalog):
            def get_lineage(self, table):
                if table.name in {"inventory", "staff", "customer"}:
                    return Lineage(upstream=("store",))
                return super().get_lineage(table)

        _, plan, _ = correr(catalog=Catalogo())
        assert not [c for c in plan.candidates if c.kind == KIND_ACTIVIDAD]
        assert not plan.corroborations

    def test_una_tabla_sin_clave_propia_no_puede_ser_ancla(self):
        anchor = TableFacts(name="store", fqn="s.store", columns=(ColumnFacts("nombre"),))
        with pytest.raises(ValueError, match="no declara una columna store_id"):
            derive_plan(anchor, [], [], concept="tienda")

    def test_una_relacion_sin_clave_de_union_se_descarta_y_se_reporta(self):
        anchor = TABLES["store"]
        huerfana = TableFacts(
            name="rental", fqn="s.rental", columns=(ColumnFacts("rental_id"),)
        )
        plan = derive_plan(anchor, [], [(huerfana, TABLES["inventory"])], concept="tienda")
        assert not [c for c in plan.candidates if c.kind == KIND_ACTIVIDAD]
        assert any("rental" in s for s in plan.skipped)


class TestElCatalogoEsEntradaNoConfiable:
    """Los nombres del catálogo los escribe gente y terminan dentro del SQL."""

    def test_un_nombre_de_tabla_con_inyeccion_no_llega_a_la_base(self):
        malicioso = TableFacts(
            name="store",
            fqn="s.store",
            schema="public; DROP TABLE store --",
            columns=(ColumnFacts("store_id"),),
        )
        with pytest.raises(UnsafeQuery, match="schema inválido"):
            derive_plan(malicioso, [], [], concept="tienda")

    def test_una_columna_con_inyeccion_no_llega_a_la_base(self):
        anchor = TableFacts(
            name="store", fqn="s.store", columns=(ColumnFacts("store_id"),)
        )
        vecina = TableFacts(
            name="customer",
            fqn="s.customer",
            columns=(ColumnFacts("store_id"), ColumnFacts("customer_id")),
        )
        # El ataque entra por el nombre de la tabla vecina, que se interpola igual.
        vecina_mala = TableFacts(
            name="customer WHERE 1=1; DROP TABLE store --",
            fqn="s.x",
            columns=(ColumnFacts("store_id"),),
        )
        derive_plan(anchor, [vecina], [], concept="tienda")  # el caso sano no levanta
        with pytest.raises(UnsafeQuery, match="tabla inválid"):
            derive_plan(anchor, [vecina_mala], [], concept="tienda")

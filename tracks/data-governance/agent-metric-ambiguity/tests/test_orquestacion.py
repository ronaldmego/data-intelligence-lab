"""Tests del orden metadata → SQL y de la compuerta que lo sostiene.

Sólo biblioteca estándar.

La afirmación central del POC es que el agente entiende antes de consultar. Un
test que se limite a mirar el trace de una corrida feliz no prueba eso: prueba
que *esa* corrida salió en ese orden. Lo que se verifica acá es más fuerte —
que la herramienta de SQL **no está disponible** hasta que hubo metadata, así
que no existe una corrida posible en el otro orden.

Por eso el doble de la base es `ExplodingSql`: si la compuerta fallara, el test
no vería un orden raro en un archivo, vería una excepción.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

import pytest  # noqa: E402
from fakes import ExplodingSql, FakeCatalog, FakeSql  # noqa: E402

from guard import UnsafeQuery  # noqa: E402
from orchestrator import GatedTools, PhaseViolation, run  # noqa: E402
from tracing import PHASE_METADATA, PHASE_SQL, Trace  # noqa: E402

PREGUNTA = "¿Cuántas tiendas tiene el negocio?"


def _tools(sql=None) -> GatedTools:
    return GatedTools(FakeCatalog(), sql or ExplodingSql(), Trace(PREGUNTA, mode="test"))


def test_la_herramienta_de_sql_esta_cerrada_al_empezar():
    tools = _tools()
    with pytest.raises(PhaseViolation, match="cerrada"):
        tools.scalar("SELECT 1")


def test_no_se_puede_abrir_la_fase_sql_sin_metadata_previa():
    tools = _tools()
    with pytest.raises(PhaseViolation, match="sin haber consultado antes el catálogo"):
        tools.open_sql_phase()


def test_se_abre_recien_despues_de_una_consulta_de_metadata():
    tools = _tools(FakeSql())
    tools.list_glossary_terms()
    tools.open_sql_phase()
    assert tools.scalar("SELECT count(*) AS value FROM public.store") == 6


def test_la_compuerta_no_es_esquivable_reordenando_las_llamadas():
    """Ni siquiera pidiendo el SQL entre dos llamadas de metadata."""
    tools = _tools()
    tools.list_glossary_terms()
    with pytest.raises(PhaseViolation):
        tools.scalar("SELECT 1")


def test_el_guard_sigue_activo_dentro_de_la_fase_sql():
    """Abrir la fase habilita leer, no escribir."""
    tools = _tools(FakeSql())
    tools.list_glossary_terms()
    tools.open_sql_phase()
    with pytest.raises(UnsafeQuery):
        tools.scalar("DROP TABLE public.store")


def test_una_consulta_rechazada_queda_registrada_en_el_trace():
    """El intento importa tanto como el bloqueo: sin registro no hay auditoría."""
    tools = _tools(FakeSql())
    tools.list_glossary_terms()
    tools.open_sql_phase()
    with pytest.raises(UnsafeQuery):
        tools.scalar("DELETE FROM public.store")
    rechazos = [s for s in tools.trace.steps if not s["ok"]]
    assert len(rechazos) == 1
    assert rechazos[0]["phase"] == PHASE_SQL
    assert "rechazada por el guard" in rechazos[0]["summary"]


class TestCorridaCompleta:
    def setup_method(self):
        self.catalog = FakeCatalog()
        self.sql = FakeSql()
        self.governance, self.plan, self.trace = run(
            PREGUNTA, self.catalog, self.sql, concept="tienda", aliases=("store",)
        )

    def test_toda_la_metadata_precede_a_todo_el_sql(self):
        fases = self.trace.phases_in_order()
        assert PHASE_METADATA in fases and PHASE_SQL in fases
        primera_sql = fases.index(PHASE_SQL)
        assert PHASE_METADATA not in fases[primera_sql:], (
            "hubo una consulta de metadata después de tocar el dato: el orden no está garantizado"
        )

    def test_el_invariante_lo_reporta_el_propio_trace(self):
        assert self.trace.metadata_precedes_sql()
        assert self.trace.to_dict()["invariants"]["metadata_before_sql"] is True

    def test_la_primera_pregunta_es_por_el_glosario(self):
        """Antes que nada: ¿alguien ya definió esto?"""
        assert self.trace.tools_in_order()[0] == "catalog.list_glossary_terms"

    def test_el_trace_registra_cada_sql_ejecutado(self):
        del_trace = [s["args"]["sql"] for s in self.trace.steps if s["tool"] == "sql.scalar"]
        assert del_trace == self.sql.executed

    def test_el_ancla_se_resuelve_al_maestro_y_no_al_primer_resultado(self):
        """La búsqueda de «tienda» también devuelve staff e inventory."""
        assert self.plan.anchor.name == "store"
        nombres = [t for _, t in self.catalog.calls if _ == "search_tables"]
        assert "tienda" in nombres

    def test_ninguna_tabla_se_consulta_dos_veces(self):
        pedidos = [arg for name, arg in self.catalog.calls if name == "get_table"]
        assert len(pedidos) == len(set(pedidos)), f"metadata repetida: {pedidos}"

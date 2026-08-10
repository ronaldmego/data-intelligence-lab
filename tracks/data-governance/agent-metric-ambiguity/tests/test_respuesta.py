"""Tests de la respuesta que ve el usuario.

Sólo biblioteca estándar.

Tres cosas que se defienden acá:

* **Que ofrezca en vez de elegir.** Con varias lecturas válidas y ninguna
  gobernada, la salida tiene que presentar las opciones con su significado, no
  devolver un número.
* **Que no invente un defecto.** El caso tienta a decir que las unidades sin
  actividad "están mal". Ni el catálogo ni las consultas sostienen esa
  afirmación, así que no puede aparecer en los hechos ni en la interpretación.
  En los límites sí aparece, negada — que es justo lo contrario.
* **Que separe hecho de opinión.** Un informe que los mezcla es correcto y
  produce decisiones equivocadas igual, porque el lector no puede auditar lo
  que no distingue.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

import pytest  # noqa: E402
from fakes import GLOSSARY_GOVERNED, FakeCatalog, FakeSql  # noqa: E402

from orchestrator import run  # noqa: E402
from report import (  # noqa: E402
    VERDICT_AMBIGUOUS,
    VERDICT_GOVERNED,
    build_answer,
    render_text,
)

PREGUNTA = "¿Cuántas tiendas tiene el negocio?"

#: Palabras que califican al dato como defectuoso. Aparecer en un hecho o en la
#: interpretación sería afirmar algo que no se midió.
JUICIOS_SIN_EVIDENCIA = ("error", "defecto", "bug", "incorrect", "mal cargad", "basura", "sucia")


def _respuesta(glossary=None):
    catalog = FakeCatalog(glossary=glossary)
    gov, plan, trace = run(PREGUNTA, catalog, FakeSql(), concept="tienda", aliases=("store",))
    return build_answer(PREGUNTA, gov, plan), plan, trace


class TestSinGobierno:
    def setup_method(self):
        self.answer, self.plan, self.trace = _respuesta()

    def test_el_veredicto_es_ambiguo(self):
        assert self.answer.verdict == VERDICT_AMBIGUOUS

    def test_ofrece_todas_las_lecturas_en_vez_de_elegir_una(self):
        assert len(self.answer.options) == 5
        valores = {o["value"] for o in self.answer.options}
        assert len(valores) == 4

    def test_cada_opcion_explica_qué_pregunta_responde(self):
        for opt in self.answer.options:
            assert opt["responde"], f"{opt['id']} no dice qué pregunta responde"
            assert opt["como_se_derivo"]
            assert opt["sql"]
            assert opt["fuentes"]

    def test_el_hecho_central_es_que_falta_el_termino(self):
        assert any("no tiene término" in f for f in self.answer.facts)
        assert self.answer.governance["termino_de_glosario"] is None

    def test_nombra_a_quien_le_corresponde_decidir(self):
        assert self.answer.governance["owners"] == ["Head of Store Operations"]
        assert any("Head of Store Operations" in i for i in self.answer.interpretation)

    def test_no_califica_de_defectuosas_a_las_unidades_sin_actividad(self):
        for linea in (*self.answer.facts, *self.answer.interpretation):
            bajo = linea.lower()
            assert not any(j in bajo for j in JUICIOS_SIN_EVIDENCIA), (
                f"afirma un defecto que no se midió: {linea}"
            )

    def test_el_limite_declara_explicitamente_esa_abstencion(self):
        assert any("no clasifica" in lim for lim in self.answer.limits)

    def test_las_tres_secciones_existen_y_no_se_pisan(self):
        assert self.answer.facts and self.answer.interpretation and self.answer.limits
        assert not set(self.answer.facts) & set(self.answer.interpretation)

    def test_cada_valor_reportado_viene_con_su_sql(self):
        for opt in self.answer.options:
            assert f"{opt['sql']}" in " ".join(self.answer.facts) or opt["sql"] in str(self.answer.options)

    def test_el_texto_renderizado_trae_las_secciones(self):
        texto = render_text(self.answer)
        for encabezado in ("OPCIONES", "GOBIERNO", "HECHOS", "INTERPRETACIÓN", "LÍMITES"):
            assert encabezado in texto

    def test_serializa_a_diccionario_completo(self):
        d = self.answer.to_dict()
        assert set(d) >= {"question", "verdict", "options", "governance", "facts", "limits"}


class TestConGobierno:
    """Con el término definido, la respuesta la decide el glosario, no el agente."""

    def setup_method(self):
        self.answer, self.plan, _ = _respuesta(glossary=GLOSSARY_GOVERNED)

    def test_el_veredicto_cambia_a_gobernada(self):
        assert self.answer.verdict == VERDICT_GOVERNED

    def test_responde_el_valor_de_la_lectura_que_el_termino_nombra(self):
        assert self.answer.headline.startswith("3.")

    def test_sigue_mostrando_las_demas_lecturas(self):
        """Que haya una definición no vuelve falsas a las otras."""
        assert len(self.answer.options) == 5

    def test_dice_que_lo_que_cierra_el_caso_es_la_definicion_y_no_el_dato(self):
        assert any("no es el dato" in i for i in self.answer.interpretation)


def test_un_termino_vago_no_resuelve_nada():
    """Media tesis del POC: definir sin decir cómo se mide no alcanza."""
    from facts import GlossaryTerm

    vago = [GlossaryTerm("Tienda", "G.Tienda", "Unidad operativa del negocio.")]
    answer, _, _ = _respuesta(glossary=vago)
    assert answer.verdict == VERDICT_AMBIGUOUS
    assert any("no nombra ninguna fuente medible" in f for f in answer.facts)


@pytest.mark.parametrize("glossary", [None, GLOSSARY_GOVERNED])
def test_siempre_se_declaran_limites(glossary):
    answer, _, _ = _respuesta(glossary=glossary)
    assert len(answer.limits) >= 3


class TestCaminosQueNoCoinciden:
    """El caso que el conteo no ve: mismos números, unidades distintas.

    Salió de la corrida real. Los cuatro caminos hacia «actividad» en Pagila
    devuelven 2 cada uno, y la primera versión de este código concluyó que
    coincidían. No coincidían: la unión daba 4, porque el camino por el empleado
    señala las tiendas 25 y 33 y el camino por el cliente señala la 1 y la 2.
    """

    def _plan(self, union_value, path_values):
        from definitions import (
            KIND_ACTIVIDAD,
            KIND_REGISTRO,
            Candidate,
            Corroboration,
            Plan,
        )
        from facts import ColumnFacts, TableFacts

        anchor = TableFacts(name="store", fqn="s.store", columns=(ColumnFacts("store_id"),))
        return Plan(
            anchor=anchor,
            key="store_id",
            candidates=(
                Candidate(
                    id="registro:store", label="Tiendas registradas", kind=KIND_REGISTRO,
                    sql="SELECT count(*) AS value FROM public.store", sources=("s.store",),
                    derivation="", meaning="", match_terms=("store",), value=500,
                ),
                Candidate(
                    id="actividad", label="Tiendas con actividad transaccional",
                    kind=KIND_ACTIVIDAD, sql="SELECT count(*) AS value FROM public.store",
                    sources=("s.payment",), derivation="", meaning="",
                    match_terms=("payment",), value=union_value,
                ),
            ),
            corroborations=tuple(
                Corroboration(
                    id=f"actividad:p{i}", label=f"camino {i}",
                    sql="SELECT count(*) AS value FROM public.store", sources=("s.x",), value=v,
                )
                for i, v in enumerate(path_values, 1)
            ),
        )

    def _answer(self, union_value, path_values):
        from facts import GovernanceFacts

        plan = self._plan(union_value, path_values)
        gov = GovernanceFacts(concept="tienda", anchor_table=plan.anchor)
        return build_answer(PREGUNTA, gov, plan)

    def test_detecta_la_divergencia_aunque_los_conteos_sean_iguales(self):
        answer = self._answer(union_value=4, path_values=[2, 2])
        assert any("no señalan las mismas unidades" in i for i in answer.interpretation)

    def test_reconoce_los_conjuntos_disjuntos(self):
        answer = self._answer(union_value=4, path_values=[2, 2])
        assert any("disjuntos" in i for i in answer.interpretation)

    def test_no_avisa_cuando_realmente_coinciden(self):
        answer = self._answer(union_value=2, path_values=[2, 2])
        assert any("señalan las mismas unidades" in i for i in answer.interpretation)
        assert not any("no señalan" in i for i in answer.interpretation)

    def test_el_solapamiento_parcial_tambien_es_divergencia(self):
        answer = self._answer(union_value=3, path_values=[2, 2])
        assert any("no señalan las mismas unidades" in i for i in answer.interpretation)
        assert not any("disjuntos" in i for i in answer.interpretation)

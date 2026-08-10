"""Armado de la respuesta: hechos, interpretación y límites, separados.

La regla que ordena este módulo: **un hecho lleva su fuente al lado y una
interpretación lleva la palabra "interpretación" encima.** Mezclarlos es la
forma más común de que un informe correcto produzca una decisión equivocada —
el lector no puede auditar lo que no distingue.

Por eso lo que el POC *no* sabe también se imprime. Un informe que sólo enumera
lo que averiguó le deja al lector la tarea de adivinar el borde.

Sin dependencias de terceros.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from definitions import KIND_ACTIVIDAD, KIND_REGISTRO, Plan
from facts import GovernanceFacts


@dataclass
class Answer:
    question: str
    concept: str
    verdict: str
    headline: str
    options: list[dict] = field(default_factory=list)
    corroborations: list[dict] = field(default_factory=list)
    governance: dict = field(default_factory=dict)
    facts: list[str] = field(default_factory=list)
    interpretation: list[str] = field(default_factory=list)
    limits: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "concept": self.concept,
            "verdict": self.verdict,
            "headline": self.headline,
            "options": self.options,
            "corroborations": self.corroborations,
            "governance": self.governance,
            "facts": self.facts,
            "interpretation": self.interpretation,
            "limits": self.limits,
        }


VERDICT_AMBIGUOUS = "ambigua"
VERDICT_SINGLE = "unica"
VERDICT_GOVERNED = "gobernada"


def _resolved_by_glossary(governance: GovernanceFacts, plan: Plan):
    """¿El término del glosario alcanza para elegir una de las lecturas?

    Heurística **declarada, no mágica**: se considera que el término resuelve la
    métrica si su definición nombra la tabla de exactamente una de las
    candidatas. Es deliberadamente literal, y el corolario es la mitad del
    argumento de gobierno: *una definición que no dice cómo se mide no resuelve
    nada*. «Unidad operativa del negocio» suena a definición y deja la pregunta
    igual de abierta que antes.
    """
    term = governance.glossary_term
    if term is None:
        return None, "sin término"
    texto = f"{term.name} {term.description}".lower()
    palabras = set(re.findall(r"[a-z_][a-z0-9_]*", texto))
    coinciden = [
        c for c in plan.candidates
        if any(term.lower() in palabras for term in c.match_terms)
    ]
    if len(coinciden) == 1:
        return coinciden[0], "el término nombra una única fuente"
    if not coinciden:
        return None, "el término no nombra ninguna fuente medible"
    return None, f"el término nombra {len(coinciden)} fuentes distintas"


def _leer_caminos(plan: Plan) -> list[str]:
    """Contrasta los caminos alternativos hacia la definición de actividad.

    **Comparar los conteos no alcanza, y creerlo suficiente fue un error real de
    este código.** Los cuatro caminos de Pagila devuelven `2` cada uno y la
    versión anterior concluyó "coinciden entre sí". No coinciden: la unión da
    `4`, porque el camino que pasa por el empleado apunta a dos tiendas y el que
    pasa por el cliente apunta a otras dos.

    Dos conjuntos del mismo tamaño pueden ser disjuntos. Lo que delata la
    diferencia es la unión, y sale gratis porque ya se calculó.
    """
    union = next((c.value for c in plan.candidates if c.kind == KIND_ACTIVIDAD), None)
    valores = [c.value for c in plan.corroborations if c.value is not None]
    if union is None or not valores:
        return []

    mayor = max(valores)
    if union <= mayor:
        return ["Los caminos alternativos hacia «actividad» señalan las mismas unidades."]

    detalle = ", ".join(f"{c.label} = {c.value}" for c in plan.corroborations)
    linea = (
        f"Los caminos alternativos hacia «actividad» **no señalan las mismas unidades**. "
        f"Cada uno cuenta a lo sumo {mayor} y la unión de todos da {union}: coinciden en el "
        f"número y difieren en a quién señalan ({detalle})."
    )
    if union == sum(valores):
        linea += (
            " La unión es exactamente la suma, así que no comparten ni una unidad: son "
            "conjuntos disjuntos."
        )
    return [
        linea,
        "Es el caso que más discretamente rompe un informe: dos consultas razonables "
        "devuelven el mismo número, las dos parecen confirmarse, y hablan de cosas distintas. "
        "Ningún control sobre el total lo detecta.",
    ]


def build_answer(question: str, governance: GovernanceFacts, plan: Plan) -> Answer:
    concept = governance.concept
    values = [c.value for c in plan.candidates if c.value is not None]
    distinct = sorted(set(values))

    elegida, motivo_glosario = _resolved_by_glossary(governance, plan)
    if elegida is not None:
        verdict = VERDICT_GOVERNED
    elif len(distinct) > 1:
        verdict = VERDICT_AMBIGUOUS
    else:
        verdict = VERDICT_SINGLE

    anchor = plan.anchor
    owners = ", ".join(governance.owners) if governance.owners else "sin owner declarado"

    if verdict == VERDICT_GOVERNED:
        headline = (
            f"{elegida.value}. El glosario define «{governance.glossary_term.name}» y su "
            f"definición apunta a «{elegida.label}», así que la respuesta no la elige el agente. "
            f"Las otras lecturas siguen abajo porque siguen siendo ciertas."
        )
    elif verdict == VERDICT_AMBIGUOUS:
        headline = (
            f"«{concept}» admite {len(distinct)} respuestas distintas "
            f"({' · '.join(str(v) for v in distinct)}) y el catálogo no dice cuál corresponde. "
            "Elegí una según para qué la necesitás."
        )
    else:
        coincidencia = distinct[0] if distinct else "ningún valor"
        headline = f"Todas las lecturas de «{concept}» coinciden en {coincidencia}."

    options = [
        {
            "id": c.id,
            "label": c.label,
            "value": c.value,
            "responde": _business_question(c.kind, concept, c.label),
            "significado_segun_catalogo": c.meaning,
            "como_se_derivo": c.derivation,
            "sql": c.sql,
            "fuentes": list(c.sources),
        }
        for c in plan.candidates
    ]

    corroborations = [
        {"id": c.id, "label": c.label, "value": c.value, "sql": c.sql, "fuentes": list(c.sources)}
        for c in plan.corroborations
    ]

    governance_block = {
        "termino_de_glosario": (
            {
                "nombre": governance.glossary_term.name,
                "fqn": governance.glossary_term.fqn,
                "definicion": governance.glossary_term.description,
            }
            if governance.glossary_term
            else None
        ),
        "terminos_buscados": list(governance.glossary_terms_searched),
        "tabla_ancla": anchor.fqn,
        "owners": list(governance.owners),
        "tier": governance.tier,
        "dominio": governance.domain,
    }

    facts: list[str] = []
    if governance.is_governed:
        term = governance.glossary_term
        facts.append(f"El glosario define «{term.name}» ({term.fqn}): {term.description}")
        facts.append(f"Resolución del término contra las lecturas disponibles: {motivo_glosario}.")
    else:
        buscados = ", ".join(f"«{w}»" for w in governance.glossary_terms_searched)
        facts.append(
            f"El glosario de negocio no tiene término para {buscados}. "
            "No existe una definición acordada de la métrica."
        )
    facts.append(
        f"El catálogo asocia el concepto a {anchor.fqn} "
        f"(tier {governance.tier or 'sin tier'}, dominio {governance.domain or 'sin dominio'}, "
        f"owner {owners})."
    )
    for c in plan.candidates:
        facts.append(f"{c.label}: {c.value} — {c.sql}")

    interpretation: list[str] = []
    if verdict == VERDICT_GOVERNED:
        interpretation.append(
            "La pregunta seguiría siendo ambigua contra el dato: las otras lecturas dan números "
            "distintos y ninguna es falsa. Lo que la cierra no es el dato, es que alguien haya "
            "escrito la definición y haya dicho cómo se mide."
        )
    elif verdict == VERDICT_AMBIGUOUS:
        registro = next((c for c in plan.candidates if c.kind == KIND_REGISTRO), None)
        menor = min((c for c in plan.candidates if c.value is not None), key=lambda c: c.value, default=None)
        if registro and menor and registro.value != menor.value:
            interpretation.append(
                f"El maestro «{anchor.name}» cuenta {registro.value} unidades y la lectura más "
                f"restrictiva cuenta {menor.value}. Las dos salen de la misma base y ninguna "
                "contradice a la otra: miden cosas distintas."
            )
        interpretation.append(
            "Con varias respuestas válidas y ninguna gobernada, responder un número solo sería "
            "una elección del agente presentada como un dato. La decisión le corresponde a "
            f"{owners}."
        )
    else:
        interpretation.append(
            "Todas las lecturas coinciden, así que la ambigüedad no cambia el resultado en este caso."
        )

    if plan.corroborations:
        facts.extend(
            f"Camino alternativo hacia «actividad» — {c.label}: {c.value} — {c.sql}"
            for c in plan.corroborations
        )
        interpretation.extend(_leer_caminos(plan))

    limits: list[str] = [
        "El POC no clasifica las unidades sin actividad. Llamarlas sobrantes, obsoletas o "
        "erróneas exigiría evidencia que ni el catálogo ni estas consultas aportan.",
        "Las definiciones salen del linaje declarado en el catálogo. Una relación real que "
        "nadie haya declarado no aparece acá.",
        "Las uniones se derivan de la convención de nombres de clave del catálogo, verificada "
        "contra sus columnas. Un modelo que no la siga produce menos definiciones, no una "
        "definición equivocada.",
    ]
    if not governance.is_governed:
        limits.append(
            "La resolución del concepto a una tabla usó el ranking de búsqueda del catálogo. "
            "Con el término de glosario definido sería exacta; sin él, en un catálogo grande "
            "sería frágil."
        )
    if plan.skipped:
        limits.append("Relaciones descartadas por falta de clave declarada: " + "; ".join(plan.skipped))

    return Answer(
        question=question,
        concept=concept,
        verdict=verdict,
        headline=headline,
        options=options,
        corroborations=corroborations,
        governance=governance_block,
        facts=facts,
        interpretation=interpretation,
        limits=limits,
    )


def _business_question(kind: str, concept: str, label: str) -> str:
    if kind == KIND_REGISTRO:
        return f"¿Cuántas {concept}s existen como registro, aunque no operen?"
    if kind == "actividad":
        return f"¿En cuántas {concept}s pasó algo que quedó registrado como transacción?"
    return f"¿En cuántas {concept}s hay presencia de lo que describe esa tabla?"


def render_text(answer: Answer) -> str:
    """Salida para terminal. Es la que se ve en la evidencia visual."""
    out: list[str] = []
    out.append(f"Pregunta: {answer.question}")
    out.append("")
    out.append(f"Veredicto: la pregunta es {answer.verdict.upper()}")
    out.append(answer.headline)
    out.append("")

    out.append("OPCIONES — elegí según la decisión que tengas que tomar")
    for i, opt in enumerate(answer.options, 1):
        out.append(f"  {i}. {opt['label']}: {opt['value']}")
        out.append(f"     responde: {opt['responde']}")
        if opt["significado_segun_catalogo"]:
            out.append(f"     el catálogo dice: {_clip(opt['significado_segun_catalogo'], 150)}")
        out.append(f"     fuentes: {', '.join(opt['fuentes'])}")
        out.append(f"     SQL: {_oneline(opt['sql'])}")
    out.append("")

    if answer.corroborations:
        out.append("CAMINOS ALTERNATIVOS (contraste de la definición de actividad)")
        for c in answer.corroborations:
            out.append(f"  - {c['label']}: {c['value']}")
        out.append("")

    out.append("GOBIERNO")
    term = answer.governance["termino_de_glosario"]
    out.append(f"  término de glosario: {term['nombre'] if term else 'NO EXISTE'}")
    out.append(f"  tabla ancla: {answer.governance['tabla_ancla']}")
    out.append(f"  owner: {', '.join(answer.governance['owners']) or 'sin owner declarado'}")
    tier = answer.governance["tier"] or "sin tier"
    dominio = answer.governance["dominio"] or "sin dominio"
    out.append(f"  tier: {tier} · dominio: {dominio}")
    out.append("")

    for title, items in (
        ("HECHOS", answer.facts),
        ("INTERPRETACIÓN", answer.interpretation),
        ("LÍMITES", answer.limits),
    ):
        out.append(title)
        for item in items:
            out.append(f"  - {item}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def _oneline(text: str) -> str:
    return " ".join(text.split())


def _clip(text: str, n: int) -> str:
    text = _oneline(text)
    return text if len(text) <= n else text[: n - 1] + "…"

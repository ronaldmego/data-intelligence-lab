"""Orquestación determinística: metadata primero, y no por buena voluntad.

La diferencia con un agente que *promete* consultar el catálogo primero está en
`GatedTools`: la herramienta de SQL no existe para quien la llame antes de
tiempo. No hay instrucción que desobedecer porque no hay puerta que abrir —
`open_sql_phase()` se niega si el trace todavía no registró una consulta de
metadata. El invariante deja de ser una observación afortunada de una corrida y
pasa a ser algo que un test afirma.

El mismo `GatedTools` lo usa la variante conducida por LLM, de modo que la
comparación entre ambas mide la conducta del modelo, no una diferencia de
frenos.

Sin dependencias de terceros.
"""

from __future__ import annotations

from typing import Protocol

from definitions import Plan, derive_plan
from facts import GlossaryTerm, GovernanceFacts, Lineage, TableFacts
from guard import UnsafeQuery, check_query
from tracing import PHASE_METADATA, PHASE_SQL, Trace


class PhaseViolation(RuntimeError):
    """Se intentó tocar el dato antes de entender qué se estaba contando."""


class CatalogPort(Protocol):
    """Lo que el POC necesita de un catálogo. Todo de lectura."""

    def list_glossary_terms(self) -> list[GlossaryTerm]: ...
    def search_tables(self, text: str, limit: int = 10) -> list[TableFacts]: ...
    def get_table(self, name: str) -> TableFacts | None: ...
    def get_lineage(self, table: TableFacts) -> Lineage: ...


class SqlPort(Protocol):
    def scalar(self, sql: str) -> int: ...


class GatedTools:
    """Envoltorio que graba cada llamada y sostiene el orden de las fases."""

    def __init__(self, catalog: CatalogPort, sql: SqlPort, trace: Trace) -> None:
        self._catalog = catalog
        self._sql = sql
        self.trace = trace
        self._sql_open = False
        # Una tabla se le pide al catálogo una sola vez por corrida. Repetir la
        # llamada no agrega evidencia y llena el trace de ruido que tapa los
        # pasos que sí importan; el recorrido del linaje pasa varias veces por
        # las mismas vecinas.
        self._tables: dict[str, TableFacts | None] = {}

    # -- metadata ----------------------------------------------------------
    #
    # Cada método graba también cuando la llamada **falla**. Parece un detalle y
    # no lo es: en la primera corrida de la variante con modelo, el catálogo
    # devolvía 401, el modelo se quedó sin contexto y el trace salió con cero
    # pasos — o sea, con la misma pinta que "el agente no consultó nada". Un
    # trace que sólo registra los éxitos hace indistinguible *no haber
    # preguntado* de *haber preguntado y que no contesten*, que son diagnósticos
    # opuestos.

    def _falla(self, tool: str, args: dict, exc: Exception) -> None:
        self.trace.record(
            phase=PHASE_METADATA,
            tool=tool,
            args=args,
            ok=False,
            summary=f"{type(exc).__name__}: {exc}",
        )

    def list_glossary_terms(self) -> list[GlossaryTerm]:
        try:
            terms = self._catalog.list_glossary_terms()
        except Exception as exc:
            self._falla("catalog.list_glossary_terms", {}, exc)
            raise
        self.trace.record(
            phase=PHASE_METADATA,
            tool="catalog.list_glossary_terms",
            summary=f"{len(terms)} términos en el glosario",
            detail=[t.name for t in terms],
        )
        return terms

    def search_tables(self, text: str, limit: int = 10) -> list[TableFacts]:
        try:
            hits = self._catalog.search_tables(text, limit=limit)
        except Exception as exc:
            self._falla("catalog.search_tables", {"text": text}, exc)
            raise
        self.trace.record(
            phase=PHASE_METADATA,
            tool="catalog.search_tables",
            args={"text": text, "limit": limit},
            summary=f"{len(hits)} tablas coinciden con «{text}»",
            detail=[h.fqn for h in hits],
        )
        return hits

    def get_table(self, name: str) -> TableFacts | None:
        if name in self._tables:
            return self._tables[name]
        try:
            table = self._catalog.get_table(name)
        except Exception as exc:
            self._falla("catalog.get_table", {"name": name}, exc)
            raise
        self._tables[name] = table
        self.trace.record(
            phase=PHASE_METADATA,
            tool="catalog.get_table",
            args={"name": name},
            ok=table is not None,
            summary=(
                f"{table.fqn} · {len(table.columns)} columnas · tier {table.tier or 'sin tier'}"
                if table
                else f"«{name}» no está en el catálogo"
            ),
        )
        return table

    def get_lineage(self, table: TableFacts) -> Lineage:
        try:
            lineage = self._catalog.get_lineage(table)
        except Exception as exc:
            self._falla("catalog.get_lineage", {"table": table.fqn}, exc)
            raise
        self.trace.record(
            phase=PHASE_METADATA,
            tool="catalog.get_lineage",
            args={"table": table.fqn},
            summary=(
                f"{len(lineage.upstream)} arriba · {len(lineage.downstream)} abajo"
            ),
            detail={"upstream": list(lineage.upstream), "downstream": list(lineage.downstream)},
        )
        return lineage

    # -- compuerta ---------------------------------------------------------

    def open_sql_phase(self) -> None:
        if not any(s["phase"] == PHASE_METADATA for s in self.trace.steps):
            raise PhaseViolation(
                "no se puede consultar el dato sin haber consultado antes el catálogo"
            )
        self._sql_open = True
        self.trace.record(
            phase=PHASE_METADATA,
            tool="orchestrator.open_sql_phase",
            summary="contexto suficiente; se habilita la consulta al dato",
        )

    # -- dato --------------------------------------------------------------

    def scalar(self, sql: str) -> int:
        if not self._sql_open:
            raise PhaseViolation(
                "la herramienta de SQL está cerrada hasta que se consulte el catálogo"
            )
        try:
            checked = check_query(sql)
        except UnsafeQuery as exc:
            self.trace.record(
                phase=PHASE_SQL,
                tool="sql.scalar",
                args={"sql": sql},
                ok=False,
                summary=f"rechazada por el guard: {exc.reason}",
            )
            raise
        value = self._sql.scalar(checked)
        self.trace.record(
            phase=PHASE_SQL,
            tool="sql.scalar",
            args={"sql": checked},
            summary=f"= {value}",
        )
        return value


def _match_term(terms: list[GlossaryTerm], concept: str) -> GlossaryTerm | None:
    """Busca el concepto entre los términos del glosario, con sus sinónimos."""
    wanted = concept.strip().lower().rstrip("s")
    for term in terms:
        names = [term.name.lower(), *(s.lower() for s in term.synonyms)]
        if any(n.rstrip("s") == wanted for n in names):
            return term
    return None


def gather_governance(tools: GatedTools, concept: str, aliases: tuple[str, ...] = ()) -> GovernanceFacts:
    """Primera pregunta del agente: ¿esto ya está definido por alguien?"""
    terms = tools.list_glossary_terms()
    searched = (concept, *aliases)
    found = None
    for word in searched:
        found = _match_term(terms, word)
        if found is not None:
            break
    return GovernanceFacts(
        concept=concept,
        glossary_term=found,
        glossary_terms_searched=searched,
    )


def resolve_anchor(
    tools: GatedTools, concept: str, aliases: tuple[str, ...] = (), explicit: str | None = None
) -> TableFacts:
    """Encuentra la tabla que representa el concepto.

    Quedarse con el primer resultado de la búsqueda no sirve: buscar «tienda»
    en este catálogo devuelve también `staff` ("Personal de tienda") e
    `inventory` ("Copias físicas de films por tienda"), y el orden lo decide un
    motor de texto que no sabe de negocio.

    La regla que sí se sostiene es estructural: **el ancla es la tabla cuya
    clave referencian las otras candidatas.** Un maestro se reconoce porque los
    demás lo apuntan a él, no porque su descripción tenga la palabra. Sale de
    las columnas que el catálogo ya declara, así que sigue siendo metadata y no
    una lista de nombres escrita a mano.

    Con el término de glosario definido nada de esto haría falta: el término
    apuntaría a su activo y la resolución sería exacta. Es otra factura de la
    misma deuda de gobierno.
    """
    if explicit:
        table = tools.get_table(explicit)
        if table is None:
            raise LookupError(f"«{explicit}» no existe en el catálogo")
        return table

    ranked: list[str] = []
    for word in (concept, *aliases):
        for hit in tools.search_tables(word):
            if hit.name not in ranked:
                ranked.append(hit.name)
    if not ranked:
        raise LookupError(f"el catálogo no tiene ninguna tabla asociada a «{concept}»")

    candidates = [t for t in (tools.get_table(n) for n in ranked) if t is not None]
    if not candidates:
        raise LookupError(f"ninguna coincidencia de «{concept}» se pudo leer del catálogo")

    wanted_names = {concept.lower(), *(a.lower() for a in aliases)}

    def referencias(table: TableFacts) -> int:
        key = f"{table.name}_id"
        if not table.has_column(key):
            return -1
        return sum(1 for other in candidates if other.name != table.name and other.has_column(key))

    scored = sorted(
        candidates,
        key=lambda t: (-referencias(t), t.name.lower() not in wanted_names, ranked.index(t.name)),
    )
    best = scored[0]
    if referencias(best) < 0:
        raise LookupError(
            f"ninguna coincidencia de «{concept}» declara una clave propia; sin eso no hay ancla"
        )

    tools.trace.record(
        phase=PHASE_METADATA,
        tool="orchestrator.resolve_anchor",
        args={"concept": concept, "aliases": list(aliases)},
        summary=f"ancla = {best.fqn} (la referencian {referencias(best)} de las coincidencias)",
        detail={t.name: referencias(t) for t in candidates},
    )
    return best


def build_plan(tools: GatedTools, anchor: TableFacts, concept: str) -> Plan:
    """Recorre el linaje para descubrir de cuántas formas se puede contar.

    Un salto: vecinas que llevan la clave del ancla. Dos saltos: tablas
    colgadas de esas vecinas que no llevan la clave pero sí la del puente —
    las transaccionales, que es donde el número se desploma.
    """
    from definitions import key_column_of

    anchor_key = key_column_of(anchor)

    direct: list[TableFacts] = []
    for name in tools.get_lineage(anchor).neighbours():
        table = tools.get_table(name)
        if table is not None and anchor_key and table.has_column(anchor_key):
            direct.append(table)

    direct_names = {t.name for t in direct}
    paths: list[tuple[TableFacts, TableFacts]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for bridge in direct:
        bridge_key = key_column_of(bridge)
        if bridge_key is None:
            continue
        for name in tools.get_lineage(bridge).neighbours():
            # El ancla y las vecinas directas ya tienen su propia definición;
            # el puente sólo sirve para llegar a lo que no la tiene.
            if name == anchor.name or name in direct_names:
                continue
            if (name, bridge.name) in seen_pairs:
                continue
            target = tools.get_table(name)
            if target is None or target.has_column(anchor_key):
                continue
            if target.has_column(bridge_key):
                paths.append((target, bridge))
                seen_pairs.add((name, bridge.name))

    return derive_plan(anchor, direct, paths, concept=concept)


def execute_plan(tools: GatedTools, plan: Plan) -> Plan:
    """Ejecuta el plan ya armado. Recién acá se toca el dato."""
    tools.open_sql_phase()
    candidates = tuple(c.with_value(tools.scalar(c.sql)) for c in plan.candidates)
    corroborations = tuple(c.with_value(tools.scalar(c.sql)) for c in plan.corroborations)
    return Plan(
        anchor=plan.anchor,
        key=plan.key,
        candidates=candidates,
        corroborations=corroborations,
        skipped=plan.skipped,
    )


def run(
    question: str,
    catalog: CatalogPort,
    sql: SqlPort,
    *,
    concept: str = "tienda",
    aliases: tuple[str, ...] = (),
    anchor: str | None = None,
) -> tuple[GovernanceFacts, Plan, Trace]:
    """Corrida completa. El orden de estas cuatro líneas *es* la tesis."""
    trace = Trace(question, mode="deterministic")
    tools = GatedTools(catalog, sql, trace)

    governance = gather_governance(tools, concept, aliases)
    anchor_table = resolve_anchor(tools, concept, aliases, explicit=anchor)
    governance.anchor_table = anchor_table
    governance.owners = anchor_table.owners
    governance.tier = anchor_table.tier
    governance.domain = anchor_table.domain

    plan = build_plan(tools, anchor_table, concept)
    plan = execute_plan(tools, plan)
    return governance, plan, trace

"""Variante conducida por un modelo, para poder comparar en vez de opinar.

Corre sobre **el mismo `GatedTools`** que la determinística: las mismas
herramientas, el mismo guard, la misma compuerta y el mismo grabador de trace.
Si algo cambia entre una corrida y otra es la conducta del modelo, no el
andamio — que es la única forma de que la comparación signifique algo.

El prompt es de **buena fe**. Sería fácil escribir uno pobre y salir a decir que
los modelos no consultan el catálogo; acá se le dice explícitamente qué se
espera, en qué orden y con qué herramientas. Lo que se mide es si lo cumple
siempre, no si puede cumplirlo alguna vez.

Nota que salió al medir: los modelos Kimi más nuevos **rechazan
`temperature: 0`** (`invalid temperature: only 1 is allowed for this model`).
No es un detalle de configuración: sin decodificación voraz no hay corridas
idénticas ni siquiera en teoría, así que la reproducibilidad de esta variante
tiene un techo que no depende del prompt.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from definitions import KIND_PRESENCIA, Candidate, Plan
from facts import GovernanceFacts, TableFacts
from guard import UnsafeQuery
from orchestrator import CatalogPort, GatedTools, PhaseViolation, SqlPort, _match_term
from tracing import Trace

DEFAULT_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.moonshot.ai/v1")
DEFAULT_MODEL = os.getenv("KIMI_MODEL", "kimi-k2.6")
MAX_STEPS = 30

SYSTEM_PROMPT = """\
Sos un agente de datos que responde preguntas de negocio sobre un catálogo de datos
gobernado (OpenMetadata) y una base PostgreSQL de solo lectura.

Regla de trabajo, en este orden:

1. Antes de tocar el dato, entendé QUÉ se te está preguntando. Empezá por el glosario
   de negocio: si el término de la pregunta está definido ahí, esa definición manda.
2. Si el glosario NO define el término, no elijas vos una definición en silencio.
   Averiguá con el catálogo qué tabla representa el concepto, qué tablas están
   conectadas a ella (linaje) y qué columnas tienen.
3. Recién entonces habilitá el SQL con open_sql_phase y contá.
4. Si la pregunta admite varias respuestas legítimas, devolvelas TODAS con su número
   y su consulta. No promedies, no elijas una, no inventes cuál es "la correcta".
   Ofrecé las opciones y explicá en qué se diferencian.

La herramienta de SQL está cerrada hasta que llames a open_sql_phase, y sólo acepta
consultas de lectura de una sola sentencia.

Cuando termines, respondé con un ÚNICO bloque JSON, sin texto alrededor:

{"definiciones": [{"etiqueta": "...", "valor": 123, "sql": "SELECT ...", "responde": "..."}],
 "ambigua": true,
 "explicacion": "en qué se diferencian las lecturas y quién debería decidir"}
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_glossary_terms",
            "description": "Términos del glosario de negocio, con su definición.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tables",
            "description": "Busca tablas en el catálogo por texto libre.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_table",
            "description": "Metadata de una tabla: descripción, owner, tier, dominio y columnas.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_lineage",
            "description": "Tablas conectadas aguas arriba y aguas abajo de una tabla.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_sql_phase",
            "description": "Habilita la consulta al dato. Exige haber consultado antes el catálogo.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sql_scalar",
            "description": "Ejecuta una consulta de lectura que devuelve un único número.",
            "parameters": {
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
            },
        },
    },
]


class LlmError(RuntimeError):
    pass


class _Session:
    def __init__(self, tools: GatedTools, concept: str, aliases: tuple[str, ...]) -> None:
        self.tools = tools
        self.concept = concept
        self.aliases = aliases
        self.terms: list = []
        self.tables: dict[str, TableFacts] = {}

    def dispatch(self, name: str, args: dict[str, Any]) -> str:
        try:
            if name == "list_glossary_terms":
                self.terms = self.tools.list_glossary_terms()
                return json.dumps(
                    [{"nombre": t.name, "definicion": t.description} for t in self.terms],
                    ensure_ascii=False,
                )
            if name == "search_tables":
                hits = self.tools.search_tables(str(args.get("text", "")))
                return json.dumps([{"nombre": h.name, "fqn": h.fqn} for h in hits], ensure_ascii=False)
            if name == "get_table":
                table = self.tools.get_table(str(args.get("name", "")))
                if table is None:
                    return json.dumps({"error": "no existe en el catálogo"}, ensure_ascii=False)
                self.tables[table.name] = table
                return json.dumps(
                    {
                        "nombre": table.name,
                        "fqn": table.fqn,
                        "schema": table.schema,
                        "descripcion": table.description,
                        "owners": list(table.owners),
                        "tier": table.tier,
                        "dominio": table.domain,
                        "columnas": [c.name for c in table.columns],
                    },
                    ensure_ascii=False,
                )
            if name == "get_lineage":
                table = self.tables.get(str(args.get("name", ""))) or self.tools.get_table(
                    str(args.get("name", ""))
                )
                if table is None:
                    return json.dumps({"error": "no existe en el catálogo"}, ensure_ascii=False)
                lin = self.tools.get_lineage(table)
                return json.dumps(
                    {"arriba": list(lin.upstream), "abajo": list(lin.downstream)}, ensure_ascii=False
                )
            if name == "open_sql_phase":
                self.tools.open_sql_phase()
                return json.dumps({"ok": "SQL habilitado"}, ensure_ascii=False)
            if name == "sql_scalar":
                value = self.tools.scalar(str(args.get("sql", "")))
                return json.dumps({"valor": value}, ensure_ascii=False)
        except PhaseViolation as exc:
            return json.dumps({"error": f"fuera de orden: {exc}"}, ensure_ascii=False)
        except UnsafeQuery as exc:
            return json.dumps({"error": f"consulta rechazada: {exc.reason}"}, ensure_ascii=False)
        except Exception as exc:  # el modelo tiene que poder recuperarse
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
        return json.dumps({"error": f"herramienta desconocida: {name}"}, ensure_ascii=False)


def _chat(messages: list[dict], *, model: str, api_key: str, base_url: str) -> dict:
    body: dict[str, Any] = {"model": model, "messages": messages, "tools": TOOLS}
    temperature = os.getenv("LLM_TEMPERATURE")
    if temperature:
        body["temperature"] = float(temperature)
    r = httpx.post(
        f"{base_url}/chat/completions",
        json=body,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=180.0,
    )
    if r.status_code != 200:
        raise LlmError(f"el proveedor respondió HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    fragment = text.strip()
    if "```" in fragment:
        parts = fragment.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                fragment = part
                break
    start, end = fragment.find("{"), fragment.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(fragment[start : end + 1])
    except json.JSONDecodeError:
        return None


def run(
    question: str,
    catalog: CatalogPort,
    sql: SqlPort,
    *,
    concept: str = "tienda",
    aliases: tuple[str, ...] = (),
    model: str | None = None,
) -> tuple[GovernanceFacts, Plan, Trace]:
    api_key = os.getenv("KIMI_API_KEY")
    if not api_key:
        raise LlmError("falta KIMI_API_KEY en el entorno")
    model = model or DEFAULT_MODEL

    trace = Trace(question, mode=f"llm:{model}")
    tools = GatedTools(catalog, sql, trace)
    session = _Session(tools, concept, aliases)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    final_text = ""
    for _ in range(MAX_STEPS):
        payload = _chat(messages, model=model, api_key=api_key, base_url=DEFAULT_BASE_URL)
        choice = payload["choices"][0]
        message = choice["message"]
        messages.append(message)
        calls = message.get("tool_calls") or []
        if not calls:
            final_text = message.get("content") or ""
            break
        for call in calls:
            fn = call["function"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = session.dispatch(fn["name"], args)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
    else:
        raise LlmError(f"el modelo no cerró en {MAX_STEPS} pasos")

    parsed = _extract_json(final_text) or {}
    trace.record(
        phase="respuesta",
        tool="llm.final",
        summary=f"{len(parsed.get('definiciones', []))} definiciones reportadas",
        detail={"ambigua": parsed.get("ambigua"), "explicacion": parsed.get("explicacion")},
    )

    anchor = session.tables.get(concept) or _guess_anchor(session, concept, aliases)
    candidates = tuple(
        Candidate(
            id=f"llm:{i}",
            label=str(d.get("etiqueta", f"lectura {i}")),
            kind=KIND_PRESENCIA,
            sql=str(d.get("sql", "")),
            sources=(anchor.fqn,) if anchor else (),
            derivation="reportada por el modelo",
            meaning=str(d.get("responde", "")),
            value=_as_int(d.get("valor")),
        )
        for i, d in enumerate(parsed.get("definiciones", []) or [], 1)
    )

    governance = GovernanceFacts(
        concept=concept,
        glossary_term=_match_term(session.terms, concept) if session.terms else None,
        glossary_terms_searched=(concept, *aliases),
        anchor_table=anchor,
        owners=anchor.owners if anchor else (),
        tier=anchor.tier if anchor else "",
        domain=anchor.domain if anchor else "",
    )
    plan = Plan(
        anchor=anchor or TableFacts(name=concept, fqn=concept),
        key="",
        candidates=candidates,
        corroborations=(),
        skipped=(),
    )
    return governance, plan, trace


def _guess_anchor(session: _Session, concept: str, aliases: tuple[str, ...]) -> TableFacts | None:
    for name in (concept, *aliases):
        if name in session.tables:
            return session.tables[name]
    return next(iter(session.tables.values()), None)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

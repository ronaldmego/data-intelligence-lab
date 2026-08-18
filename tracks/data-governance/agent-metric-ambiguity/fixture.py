"""Captura y reproducción de una corrida.

Una corrida viva necesita OpenMetadata levantado, la base con Pagila y estar
dentro del tailnet. Nada de eso existe en la CI ni en la máquina de quien lea
el repositorio, así que sin esto el "ejemplo reproducible" sería una captura de
pantalla.

Lo que se graba es **lo que respondieron los servicios**, no lo que el POC
concluyó. La conclusión se vuelve a calcular al reproducir: si alguien toca la
derivación, la corrida offline cambia y el test lo delata. Un fixture que
guardara la respuesta final sería un test de que el archivo no cambió.

Se sanea con el mismo `trace.sanitize` que el trace, por la misma razón: si
sanear fuera un paso posterior, la versión sucia existiría en disco.

Sin dependencias de terceros.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from facts import ColumnFacts, GlossaryTerm, Lineage, TableFacts
from tracing import sanitize

FIXTURE_VERSION = 1


def redact_host(url: str) -> str:
    """Deja el esquema y el puerto, borra el host.

    Este repositorio es público y la instancia vive en una red privada. La
    dirección no es un secreto —no abre nada por sí sola— pero publicar
    direcciones internas de infraestructura es regalar mapa sin necesidad: para
    reproducir el caso sirve saber que era OpenMetadata en su puerto, no dónde
    está.
    """
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    host_port = rest.split("/", 1)[0]
    port = host_port.rsplit(":", 1)[-1] if ":" in host_port else ""
    return f"{scheme}://host-interno{':' + port if port else ''}"


# -- serialización ---------------------------------------------------------


def _table_to_dict(t: TableFacts) -> dict[str, Any]:
    return {
        "name": t.name,
        "fqn": t.fqn,
        "schema": t.schema,
        "description": t.description,
        "owners": list(t.owners),
        "tier": t.tier,
        "domain": t.domain,
        "columns": [
            {"name": c.name, "data_type": c.data_type, "description": c.description}
            for c in t.columns
        ],
    }


def _table_from_dict(d: dict[str, Any]) -> TableFacts:
    return TableFacts(
        name=d["name"],
        fqn=d["fqn"],
        schema=d.get("schema", "public"),
        description=d.get("description", ""),
        owners=tuple(d.get("owners") or ()),
        tier=d.get("tier", ""),
        domain=d.get("domain", ""),
        columns=tuple(
            ColumnFacts(c["name"], c.get("data_type", ""), c.get("description", ""))
            for c in d.get("columns") or []
        ),
    )


def _term_to_dict(t: GlossaryTerm) -> dict[str, Any]:
    return {
        "name": t.name,
        "fqn": t.fqn,
        "description": t.description,
        "synonyms": list(t.synonyms),
    }


def _term_from_dict(d: dict[str, Any]) -> GlossaryTerm:
    return GlossaryTerm(
        name=d["name"],
        fqn=d.get("fqn", d["name"]),
        description=d.get("description", ""),
        synonyms=tuple(d.get("synonyms") or ()),
    )


# -- grabación -------------------------------------------------------------


class RecordingCatalog:
    """Envuelve un catálogo vivo y guarda cada respuesta."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.data: dict[str, Any] = {"glossary_terms": [], "search": {}, "tables": {}, "lineage": {}}

    def list_glossary_terms(self) -> list[GlossaryTerm]:
        terms = self._inner.list_glossary_terms()
        self.data["glossary_terms"] = [_term_to_dict(t) for t in terms]
        return terms

    def search_tables(self, text: str, limit: int = 10) -> list[TableFacts]:
        hits = self._inner.search_tables(text, limit=limit)
        self.data["search"][text] = [_table_to_dict(h) for h in hits]
        return hits

    def get_table(self, name: str) -> TableFacts | None:
        table = self._inner.get_table(name)
        self.data["tables"][name] = _table_to_dict(table) if table else None
        return table

    def get_lineage(self, table: TableFacts) -> Lineage:
        lineage = self._inner.get_lineage(table)
        self.data["lineage"][table.fqn] = {
            "upstream": list(lineage.upstream),
            "downstream": list(lineage.downstream),
        }
        return lineage


class RecordingSql:
    def __init__(self, inner) -> None:
        self._inner = inner
        self.data: dict[str, int] = {}

    def scalar(self, sql: str) -> int:
        value = self._inner.scalar(sql)
        self.data[sql] = value
        return value


def save_capture(
    path: str | Path,
    *,
    catalog: RecordingCatalog,
    sql: RecordingSql,
    metadata: dict[str, Any] | None = None,
) -> Path:
    payload = {
        "fixture_version": FIXTURE_VERSION,
        "about": (
            "Respuestas reales de OpenMetadata y PostgreSQL, saneadas. La conclusión "
            "no se guarda: se recalcula al reproducir."
        ),
        "source": sanitize(metadata or {}),
        "catalog": sanitize(catalog.data),
        "sql": sanitize(sql.data),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# -- reproducción ----------------------------------------------------------


class FixtureCatalog:
    """Implementa `CatalogPort` sobre una captura."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def list_glossary_terms(self) -> list[GlossaryTerm]:
        return [_term_from_dict(d) for d in self._data.get("glossary_terms", [])]

    def search_tables(self, text: str, limit: int = 10) -> list[TableFacts]:
        hits = self._data.get("search", {}).get(text)
        if hits is None:
            return []
        return [_table_from_dict(d) for d in hits][:limit]

    def get_table(self, name: str) -> TableFacts | None:
        d = self._data.get("tables", {}).get(name)
        return _table_from_dict(d) if d else None

    def get_lineage(self, table: TableFacts) -> Lineage:
        d = self._data.get("lineage", {}).get(table.fqn)
        if not d:
            return Lineage()
        return Lineage(upstream=tuple(d.get("upstream", ())), downstream=tuple(d.get("downstream", ())))


class FixtureSql:
    """Implementa `SqlPort` sobre una captura.

    Una consulta que no esté en la captura levanta en vez de devolver cero: si
    la derivación cambió, el fixture quedó viejo y hay que volver a capturar.
    Devolver un valor por omisión escondería exactamente eso.
    """

    def __init__(self, data: dict[str, int]) -> None:
        self._data = dict(data)
        self.executed: list[str] = []

    def scalar(self, sql: str) -> int:
        self.executed.append(sql)
        if sql not in self._data:
            raise KeyError(
                "esta consulta no está en la captura; la derivación cambió y hay que "
                f"volver a capturar contra los servicios vivos:\n{sql}"
            )
        return self._data[sql]


def load_capture(path: str | Path) -> tuple[FixtureCatalog, FixtureSql, dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    version = payload.get("fixture_version")
    if version != FIXTURE_VERSION:
        raise ValueError(f"captura de versión {version}; este código espera {FIXTURE_VERSION}")
    return (
        FixtureCatalog(payload.get("catalog", {})),
        FixtureSql(payload.get("sql", {})),
        payload.get("source", {}),
    )

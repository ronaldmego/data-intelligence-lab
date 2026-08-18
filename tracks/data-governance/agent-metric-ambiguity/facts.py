"""Hechos de catálogo: lo que el agente sabe *antes* de tocar el dato.

Son estructuras planas a propósito. El adaptador de OpenMetadata las llena
desde la API y los tests las llenan a mano, de modo que el orquestador no
distingue una corrida viva de una con fixtures — que es lo que permite probarlo
en CI sin levantar servicios.

Sin dependencias de terceros.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ColumnFacts:
    name: str
    data_type: str = ""
    description: str = ""


@dataclass(frozen=True)
class TableFacts:
    """Una tabla tal como la describe el catálogo, no la base."""

    name: str
    fqn: str
    schema: str = "public"
    description: str = ""
    owners: tuple[str, ...] = ()
    tier: str = ""
    domain: str = ""
    columns: tuple[ColumnFacts, ...] = ()

    def has_column(self, name: str) -> bool:
        return any(c.name == name for c in self.columns)

    def column_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)


@dataclass(frozen=True)
class GlossaryTerm:
    name: str
    fqn: str
    description: str = ""
    synonyms: tuple[str, ...] = ()


@dataclass(frozen=True)
class Lineage:
    """Vecinos declarados de una entidad, ya normalizados a nombres de tabla.

    El adaptador se encarga del formato real de OpenMetadata, que devuelve las
    aristas como diccionarios indexados por ``"origen--->destino"`` y no como
    listas.
    """

    upstream: tuple[str, ...] = ()
    downstream: tuple[str, ...] = ()

    def neighbours(self) -> tuple[str, ...]:
        seen: list[str] = []
        for n in (*self.downstream, *self.upstream):
            if n not in seen:
                seen.append(n)
        return tuple(seen)


@dataclass
class GovernanceFacts:
    """Qué dice el catálogo sobre *cómo se gobierna* el concepto preguntado.

    El campo que decide el comportamiento del agente es `glossary_term`: si es
    `None`, no existe una definición acordada del término y cualquier número que
    el agente devuelva sería una elección suya disfrazada de dato.
    """

    concept: str
    glossary_term: GlossaryTerm | None = None
    glossary_terms_searched: tuple[str, ...] = ()
    anchor_table: TableFacts | None = None
    owners: tuple[str, ...] = ()
    tier: str = ""
    domain: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def is_governed(self) -> bool:
        return self.glossary_term is not None

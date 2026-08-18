"""Derivación de las definiciones candidatas a partir del catálogo.

Éste es el módulo que decide si el POC es honesto o es una puesta en escena.

La tentación es escribir las cinco consultas a mano y decir que "el agente
consultó el catálogo". Acá no hay ninguna consulta escrita a mano: cada
definición sale de tres cosas que el catálogo dice y el código no sabe de
antemano — qué tabla representa el concepto, qué tablas están conectadas a ella
(linaje) y qué columnas tiene cada una. Cambiá el catálogo y cambian las
definiciones; apuntá el POC a otro dominio y sigue funcionando.

Consecuencia incómoda pero necesaria: el contenido del catálogo es **entrada no
confiable**. Los nombres los escribe gente y acá terminan dentro de una
sentencia SQL, donde un identificador no se puede pasar como parámetro. Por eso
todo nombre pasa por `guard.safe_identifier` antes de ser interpolado.

Sin dependencias de terceros.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from facts import TableFacts
from guard import check_query, safe_identifier

#: Convención de nombre de clave que este catálogo cumple: la clave primaria de
#: la tabla `x` se llama `x_id`, y una tabla que referencia a `x` lleva una
#: columna con ese mismo nombre. Se **verifica** contra las columnas del
#: catálogo antes de usarse (`key_column_of`), no se asume. Un catálogo que no
#: la cumpla hace que la derivación no encuentre candidatas, que es el fallo
#: correcto: mejor no derivar nada que derivar un join inventado.
KEY_SUFFIX = "_id"

KIND_REGISTRO = "registro"
KIND_PRESENCIA = "presencia"
KIND_ACTIVIDAD = "actividad"


@dataclass(frozen=True)
class Candidate:
    """Una forma legítima de contar el concepto, con su procedencia."""

    id: str
    label: str
    kind: str
    sql: str
    sources: tuple[str, ...]
    derivation: str
    meaning: str
    #: Tablas que *identifican* la lectura, sin los puentes que sólo sirven para
    #: llegar a ella. `sources` lista todo lo que la consulta toca —el puente
    #: incluido— y por eso no sirve para decidir a cuál lectura apunta una
    #: definición de glosario: `inventory` aparece tanto en la lectura de
    #: inventario como de puente en la de actividad, y el empate hacía que un
    #: término perfectamente claro no resolviera nada.
    match_terms: tuple[str, ...] = ()
    value: int | None = None

    def with_value(self, value: int) -> Candidate:
        return replace(self, value=value)


@dataclass(frozen=True)
class Corroboration:
    """Un camino alternativo hacia la misma definición.

    Sirve para detectar el caso en que dos rutas igual de válidas no coinciden:
    el importe pagado por el cliente de una tienda y el procesado por el
    empleado de otra no tienen por qué contarse igual. Si divergen, no es un
    bug del POC — es un hallazgo.
    """

    id: str
    label: str
    sql: str
    sources: tuple[str, ...]
    value: int | None = None

    def with_value(self, value: int) -> Corroboration:
        return replace(self, value=value)


@dataclass(frozen=True)
class Plan:
    anchor: TableFacts
    key: str
    candidates: tuple[Candidate, ...]
    corroborations: tuple[Corroboration, ...]
    skipped: tuple[str, ...] = ()


def key_column_of(table: TableFacts) -> str | None:
    """Nombre de la clave de la tabla, si el catálogo confirma que existe."""
    candidate = f"{table.name}{KEY_SUFFIX}"
    return candidate if table.has_column(candidate) else None


def _qualified(table: TableFacts) -> str:
    schema = safe_identifier(table.schema, kind="schema")
    name = safe_identifier(table.name, kind="tabla")
    return f"{schema}.{name}"


def _sql_count_rows(table: TableFacts) -> str:
    return f"SELECT count(*) AS value FROM {_qualified(table)}"


def _sql_count_distinct(table: TableFacts, key: str) -> str:
    key = safe_identifier(key, kind="columna")
    return f"SELECT count(DISTINCT t.{key}) AS value FROM {_qualified(table)} t"


def _sql_path_select(target: TableFacts, bridge: TableFacts, bridge_key: str, anchor_key: str) -> str:
    """Sub-consulta de un camino de dos saltos: objetivo → puente → ancla."""
    anchor_key = safe_identifier(anchor_key, kind="columna")
    bridge_key = safe_identifier(bridge_key, kind="columna")
    return (
        f"SELECT DISTINCT j.{anchor_key} AS {anchor_key} "
        f"FROM {_qualified(target)} t "
        f"JOIN {_qualified(bridge)} j ON j.{bridge_key} = t.{bridge_key}"
    )


def _sql_path_count(target: TableFacts, bridge: TableFacts, bridge_key: str, anchor_key: str) -> str:
    anchor_key = safe_identifier(anchor_key, kind="columna")
    bridge_key = safe_identifier(bridge_key, kind="columna")
    return (
        f"SELECT count(DISTINCT j.{anchor_key}) AS value "
        f"FROM {_qualified(target)} t "
        f"JOIN {_qualified(bridge)} j ON j.{bridge_key} = t.{bridge_key}"
    )


def _sql_union_count(paths: list[tuple[TableFacts, TableFacts, str]], anchor_key: str) -> str:
    """Cuenta el ancla alcanzable por **cualquiera** de los caminos.

    Es la lectura generosa de "actividad": una tienda cuenta si aparece en al
    menos una transacción, sin privilegiar una ruta sobre otra. Elegir una sola
    ruta sería volver a hacer en silencio lo que este POC critica.
    """
    inner = "\nUNION\n".join(
        _sql_path_select(target, bridge, bridge_key, anchor_key)
        for target, bridge, bridge_key in paths
    )
    return f"SELECT count(*) AS value FROM (\n{inner}\n) u"


def derive_plan(
    anchor: TableFacts,
    direct: list[TableFacts],
    paths: list[tuple[TableFacts, TableFacts]],
    *,
    concept: str,
) -> Plan:
    """Arma el plan de consultas desde los hechos del catálogo.

    Args:
        anchor: la tabla que representa el concepto preguntado.
        direct: tablas vecinas que llevan la clave del ancla.
        paths: pares (objetivo, puente) donde el objetivo **no** lleva la clave
            del ancla pero sí la del puente, que a su vez sí la lleva.
        concept: cómo se nombra el concepto en la pregunta ("tienda").
    """
    anchor_key = key_column_of(anchor)
    if anchor_key is None:
        raise ValueError(
            f"el catálogo no declara una columna {anchor.name}{KEY_SUFFIX} en {anchor.fqn}; "
            "sin clave no hay forma de derivar definiciones sin inventar el join"
        )

    candidates: list[Candidate] = [
        Candidate(
            id=f"{KIND_REGISTRO}:{anchor.name}",
            label=f"{concept.capitalize()}s registradas",
            kind=KIND_REGISTRO,
            sql=check_query(_sql_count_rows(anchor)),
            sources=(anchor.fqn,),
            derivation=(
                f"Filas del maestro «{anchor.name}», la tabla que el catálogo asocia al concepto."
            ),
            meaning=anchor.description,
            match_terms=(anchor.name,),
        )
    ]

    skipped: list[str] = []

    for table in sorted(direct, key=lambda t: t.name):
        if not table.has_column(anchor_key):
            skipped.append(f"{table.name}: no lleva la columna {anchor_key}")
            continue
        candidates.append(
            Candidate(
                id=f"{KIND_PRESENCIA}:{table.name}",
                label=f"{concept.capitalize()}s presentes en «{table.name}»",
                kind=KIND_PRESENCIA,
                sql=check_query(_sql_count_distinct(table, anchor_key)),
                sources=(table.fqn,),
                derivation=(
                    f"Valores distintos de {anchor_key} en «{table.name}», que el linaje "
                    f"declara conectada a «{anchor.name}» y cuyas columnas incluyen esa clave."
                ),
                meaning=table.description,
                match_terms=(table.name,),
            )
        )

    usable: list[tuple[TableFacts, TableFacts, str]] = []
    for target, bridge in sorted(paths, key=lambda p: (p[0].name, p[1].name)):
        bridge_key = key_column_of(bridge)
        if bridge_key is None or not target.has_column(bridge_key):
            skipped.append(f"{target.name} vía {bridge.name}: no hay clave de unión declarada")
            continue
        if not bridge.has_column(anchor_key):
            skipped.append(f"{target.name} vía {bridge.name}: el puente no lleva {anchor_key}")
            continue
        usable.append((target, bridge, bridge_key))

    corroborations: list[Corroboration] = []
    if usable:
        targets = sorted({t.name for t, _, _ in usable})
        candidates.append(
            Candidate(
                id=KIND_ACTIVIDAD,
                label=f"{concept.capitalize()}s con actividad transaccional",
                kind=KIND_ACTIVIDAD,
                sql=check_query(_sql_union_count(usable, anchor_key)),
                sources=tuple(sorted({t.fqn for t, _, _ in usable} | {b.fqn for _, b, _ in usable})),
                derivation=(
                    "Unión de los caminos de dos saltos que el linaje declara desde "
                    f"«{anchor.name}» hasta {', '.join('«' + t + '»' for t in targets)}: "
                    "una unidad cuenta si aparece en al menos una transacción."
                ),
                meaning="; ".join(
                    f"{t.name}: {t.description}"
                    for t in sorted({t for t, _, _ in usable}, key=lambda x: x.name)
                ),
                match_terms=tuple(targets),
            )
        )
        for target, bridge, bridge_key in usable:
            corroborations.append(
                Corroboration(
                    id=f"{KIND_ACTIVIDAD}:{target.name}:{bridge.name}",
                    label=f"«{target.name}» vía «{bridge.name}»",
                    sql=check_query(_sql_path_count(target, bridge, bridge_key, anchor_key)),
                    sources=(target.fqn, bridge.fqn),
                )
            )

    return Plan(
        anchor=anchor,
        key=anchor_key,
        candidates=tuple(candidates),
        corroborations=tuple(corroborations),
        skipped=tuple(skipped),
    )

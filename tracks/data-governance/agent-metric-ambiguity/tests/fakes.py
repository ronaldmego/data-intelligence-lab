"""Catálogo y base sintéticos para los tests.

Dos decisiones deliberadas.

**El catálogo es sintético y mínimo, no una copia de Pagila.** Si los tests
corrieran contra una foto del catálogo real, pasarían por reconocer los nombres
en vez de por ejercitar la derivación. Acá los nombres son los mismos pero el
contenido es de juguete y los números se verifican a mano.

**La base es `sqlite3` de verdad, no un diccionario.** Un doble que devuelve
números preacordados prueba que el orquestador sabe leer un diccionario. Con
sqlite, el SQL que la derivación arma se ejecuta de verdad: si genera un join
mal escrito, el test falla con un error de sintaxis en vez de pasar. Es
biblioteca estándar, así que la CI lo corre sin instalar nada.

El esquema `public` existe en sqlite vía `ATTACH`, para que los nombres
calificados que produce la derivación funcionen igual que en PostgreSQL.
"""

from __future__ import annotations

import sqlite3

from facts import ColumnFacts, GlossaryTerm, Lineage, TableFacts

SERVICE = "pagila_source.pagila.public"


def _t(name: str, columns: list[str], description: str = "", **kw) -> TableFacts:
    return TableFacts(
        name=name,
        fqn=f"{SERVICE}.{name}",
        schema="public",
        description=description or f"Tabla {name} de prueba.",
        columns=tuple(ColumnFacts(name=c, data_type="integer") for c in columns),
        **kw,
    )


TABLES: dict[str, TableFacts] = {
    "store": _t(
        "store",
        ["store_id", "manager_staff_id", "address_id"],
        "Tiendas físicas: dirección y staff manager. Unidad operativa que posee inventario.",
        owners=("Head of Store Operations",),
        tier="Tier.Tier2",
        domain="RentalOperations",
    ),
    "staff": _t("staff", ["staff_id", "store_id", "address_id"], "Personal de tienda."),
    "customer": _t("customer", ["customer_id", "store_id", "address_id"], "Registro maestro de clientes."),
    "inventory": _t(
        "inventory", ["inventory_id", "film_id", "store_id"], "Copias físicas de films por tienda."
    ),
    "rental": _t(
        "rental", ["rental_id", "inventory_id", "customer_id", "staff_id"], "Transacciones de alquiler."
    ),
    "payment": _t("payment", ["payment_id", "customer_id", "staff_id", "rental_id"], "Pagos de clientes."),
    "address": _t("address", ["address_id", "city_id"], "Direcciones."),
    "film": _t("film", ["film_id", "title"], "Catálogo de películas."),
}

LINEAGE: dict[str, Lineage] = {
    "store": Lineage(downstream=("inventory", "staff", "customer")),
    "inventory": Lineage(upstream=("store", "film"), downstream=("rental",)),
    "staff": Lineage(upstream=("store", "address"), downstream=("payment",)),
    "customer": Lineage(upstream=("store", "address"), downstream=("rental", "payment")),
    "rental": Lineage(upstream=("inventory", "customer"), downstream=("payment",)),
    "payment": Lineage(upstream=("rental", "customer", "staff")),
    "address": Lineage(downstream=("customer", "staff")),
    "film": Lineage(downstream=("inventory",)),
}

#: El glosario tiene términos de negocio pero **ninguno para «tienda»**. Ésa es
#: la condición que hace ambigua la pregunta, así que es parte del fixture.
GLOSSARY = [
    GlossaryTerm("Film", "DemoGlossary.Catalogo.Film", "Película del catálogo."),
    GlossaryTerm("Inventory", "DemoGlossary.Catalogo.Inventory", "Copia física de un film en una tienda."),
    GlossaryTerm("Rental", "DemoGlossary.Alquiler.Rental", "Transacción de alquiler."),
    GlossaryTerm("Payment", "DemoGlossary.Finanzas.Payment", "Pago asociado a un alquiler."),
]

#: Variante gobernada: el mismo glosario con el término definido. Sirve para
#: comprobar que el agente cambia de conducta cuando la definición existe.
GLOSSARY_GOVERNED = [
    *GLOSSARY,
    GlossaryTerm(
        "Tienda",
        "DemoGlossary.Operacion.Tienda",
        "Unidad operativa con inventario asignado: se cuenta por presencia en inventory.",
        synonyms=("Store",),
    ),
]


class FakeCatalog:
    """Implementa `CatalogPort` sobre las estructuras de arriba."""

    def __init__(self, glossary: list[GlossaryTerm] | None = None) -> None:
        self.glossary = GLOSSARY if glossary is None else glossary
        self.calls: list[tuple[str, str]] = []

    def list_glossary_terms(self) -> list[GlossaryTerm]:
        self.calls.append(("list_glossary_terms", ""))
        return list(self.glossary)

    def search_tables(self, text: str, limit: int = 10) -> list[TableFacts]:
        self.calls.append(("search_tables", text))
        needle = text.lower().rstrip("s")
        hits = [t for t in TABLES.values() if needle in t.description.lower() or needle in t.name]
        # El maestro primero, como haría el ranking de un catálogo real.
        hits.sort(key=lambda t: (needle not in t.name, t.name))
        return hits[:limit]

    def get_table(self, name: str) -> TableFacts | None:
        self.calls.append(("get_table", name))
        return TABLES.get(name)

    def get_lineage(self, table: TableFacts) -> Lineage:
        self.calls.append(("get_lineage", table.name))
        return LINEAGE.get(table.name, Lineage())


#: Dataset de juguete. Los cinco números que debe producir el POC salen de acá y
#: se pueden contar a mano:
#:   registradas 6 · staff 4 · inventario 3 · clientes 2 · actividad 2
ROWS = {
    "store": [(i, i, i) for i in range(1, 7)],
    "staff": [(1, 1, 1), (2, 2, 2), (3, 3, 3), (4, 4, 4), (5, 4, 5)],
    "customer": [(1, 1, 1), (2, 1, 2), (3, 2, 3)],
    "inventory": [(1, 10, 1), (2, 10, 2), (3, 11, 3), (4, 12, 1)],
    "rental": [(1, 1, 1, 1), (2, 2, 2, 2), (3, 4, 3, 1)],
    "payment": [(1, 1, 1, 1), (2, 2, 2, 2), (3, 3, 1, 3)],
    "address": [(i, i) for i in range(1, 6)],
    "film": [(10, "a"), (11, "b"), (12, "c")],
}

EXPECTED = {
    "registro:store": 6,
    "presencia:staff": 4,
    "presencia:inventory": 3,
    "presencia:customer": 2,
    "actividad": 2,
}


def build_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("ATTACH DATABASE ':memory:' AS public")
    for name, table in TABLES.items():
        cols = ", ".join(f"{c.name} {'TEXT' if c.name == 'title' else 'INTEGER'}" for c in table.columns)
        conn.execute(f"CREATE TABLE public.{name} ({cols})")
        rows = ROWS[name]
        if rows:
            placeholders = ", ".join("?" for _ in table.columns)
            conn.executemany(f"INSERT INTO public.{name} VALUES ({placeholders})", rows)
    conn.commit()
    return conn


class FakeSql:
    """Implementa `SqlPort` ejecutando el SQL derivado contra sqlite."""

    def __init__(self) -> None:
        self.conn = build_sqlite()
        self.executed: list[str] = []

    def scalar(self, sql: str) -> int:
        self.executed.append(sql)
        row = self.conn.execute(sql).fetchone()
        return int(row[0])


class ExplodingSql:
    """`SqlPort` que falla si alguien la llama. Para probar la compuerta."""

    def scalar(self, sql: str) -> int:  # pragma: no cover - debe no llamarse
        raise AssertionError(f"se tocó el dato cuando no correspondía: {sql!r}")

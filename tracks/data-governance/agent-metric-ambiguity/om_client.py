"""Adaptador de solo lectura contra la API REST de OpenMetadata.

Traduce lo que devuelve OM a los `facts` que el orquestador entiende. Toda la
fealdad de la API vive acá para que el núcleo siga siendo importable sin
dependencias — la CI corre los tests con `uvx pytest`, que no instala nada.

**Solo lectura, sin excusas.** Este módulo no tiene `post`, `put` ni `patch`.
No es que no se usen: no existen. El proyecto hermano `openmetadata-mcp-agent`
publica diez herramientas que mutan el catálogo (descripciones, owners,
glosarios, tags, dominios); reutilizarlo entero habría metido en este flujo
exactamente lo que el POC promete no tener.

Dos formas de la API que ya costaron diagnósticos falsos en esta flota y que
acá están resueltas de entrada:

* `upstreamEdges` / `downstreamEdges` **son diccionarios**, indexados por
  ``"<fqn origen>--->​<fqn destino>"``. Iterarlos directo devuelve las claves,
  que son strings, y revienta con `TypeError: string indices must be integers`
  — un error que no menciona linaje por ningún lado. Hay que recorrer
  `.values()`.
* El login manda el password en **base64**; `changePassword` lo manda en claro.
  Confundirlos da "Old Password is not correct" y manda a buscar el problema a
  la credencial, que está bien.
"""

from __future__ import annotations

import base64
import os
from typing import Any

import httpx

from facts import ColumnFacts, GlossaryTerm, Lineage, TableFacts

DEFAULT_TIMEOUT = 30.0


class OpenMetadataError(RuntimeError):
    pass


class OpenMetadataCatalog:
    """Implementa `CatalogPort` contra una instancia real."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        email: str | None = None,
        password: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)
        self._token = token or self._login(email, password)

    # -- infraestructura ---------------------------------------------------

    def _login(self, email: str | None, password: str | None) -> str:
        if not email or not password:
            raise OpenMetadataError(
                "hacen falta credenciales: pasá un token o un par email/password"
            )
        encoded = base64.b64encode(password.encode()).decode()
        r = self._client.post(
            f"{self.base_url}/api/v1/users/login",
            json={"email": email, "password": encoded},
        )
        if r.status_code != 200:
            # El cuerpo puede traer el eco de la credencial; nunca se propaga.
            raise OpenMetadataError(f"login rechazado por OpenMetadata (HTTP {r.status_code})")
        return r.json()["accessToken"]

    def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        r = self._client.get(
            f"{self.base_url}/api/v1{path}",
            params=params,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        if r.status_code == 404:
            raise LookupError(path)
        if r.status_code != 200:
            raise OpenMetadataError(f"GET {path} -> HTTP {r.status_code}")
        return r.json()

    def version(self) -> str:
        try:
            return self._get("/system/version").get("version", "desconocida")
        except Exception:
            return "desconocida"

    def close(self) -> None:
        self._client.close()

    # -- CatalogPort -------------------------------------------------------

    def list_glossary_terms(self, limit: int = 200) -> list[GlossaryTerm]:
        data = self._get("/glossaryTerms", {"limit": limit, "fields": "glossary"}).get("data", [])
        return [
            GlossaryTerm(
                name=t.get("name", ""),
                fqn=t.get("fullyQualifiedName", t.get("name", "")),
                description=_plain(t.get("description", "")),
                synonyms=tuple(t.get("synonyms") or ()),
            )
            for t in data
        ]

    def search_tables(self, text: str, limit: int = 10) -> list[TableFacts]:
        payload = self._get(
            "/search/query",
            {"q": text, "index": "table_search_index", "size": limit, "from": 0},
        )
        hits = payload.get("hits", {}).get("hits", [])
        out: list[TableFacts] = []
        for hit in hits:
            src = hit.get("_source", {})
            fqn = src.get("fullyQualifiedName")
            if not fqn:
                continue
            out.append(
                TableFacts(
                    name=src.get("name", fqn.rsplit(".", 1)[-1]),
                    fqn=fqn,
                    schema=_schema_of(fqn),
                    description=_plain(src.get("description", "")),
                )
            )
        return out

    def get_table(self, name: str) -> TableFacts | None:
        """Acepta un nombre corto o un FQN completo.

        Con nombre corto hay que resolver el FQN primero: `/tables/name/<x>`
        exige el calificado, y pedirlo con el corto da un 404 que se lee como
        "la tabla no existe" cuando en realidad existe.
        """
        fqn = name if name.count(".") >= 3 else self._resolve_fqn(name)
        if fqn is None:
            return None
        try:
            t = self._get(
                f"/tables/name/{fqn}",
                {"fields": "columns,owners,tags,domains,dataProducts"},
            )
        except LookupError:
            return None
        return _to_table_facts(t)

    def _resolve_fqn(self, short_name: str) -> str | None:
        for hit in self.search_tables(short_name, limit=25):
            if hit.name == short_name:
                return hit.fqn
        return None

    def get_lineage(self, table: TableFacts) -> Lineage:
        try:
            payload = self._get(
                "/lineage/getLineage",
                {
                    "fqn": table.fqn,
                    "type": "table",
                    "upstreamDepth": 1,
                    "downstreamDepth": 1,
                },
            )
        except (LookupError, OpenMetadataError):
            return Lineage()
        return Lineage(
            upstream=_edge_names(payload.get("upstreamEdges"), "fromEntity", table.fqn),
            downstream=_edge_names(payload.get("downstreamEdges"), "toEntity", table.fqn),
        )


# -- traducción ------------------------------------------------------------


def _edges(raw: Any) -> list[dict]:
    """Normaliza las aristas de linaje.

    OM las devuelve como **diccionario** indexado por ``"origen--->destino"``.
    Se admite también la forma de lista por si una versión la cambia, en vez de
    romper de una forma que no menciona el linaje.
    """
    if isinstance(raw, dict):
        return [e for e in raw.values() if isinstance(e, dict)]
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    return ()  # type: ignore[return-value]


def _edge_names(raw: Any, side: str, self_fqn: str) -> tuple[str, ...]:
    names: list[str] = []
    for edge in _edges(raw):
        entity = edge.get(side) or {}
        fqn = entity.get("fullyQualifiedName")
        if not fqn or fqn == self_fqn:
            continue
        short = fqn.rsplit(".", 1)[-1]
        if short not in names:
            names.append(short)
    return tuple(names)


def _to_table_facts(t: dict) -> TableFacts:
    fqn = t.get("fullyQualifiedName", "")
    tags = t.get("tags") or []
    tier = next(
        (tag.get("tagFQN", "") for tag in tags if str(tag.get("tagFQN", "")).startswith("Tier.")),
        "",
    )
    domains = t.get("domains") or ([t["domain"]] if t.get("domain") else [])
    domain = ", ".join(d.get("name", "") for d in domains if isinstance(d, dict))
    owners = tuple(
        o.get("displayName") or o.get("name", "")
        for o in (t.get("owners") or [])
        if isinstance(o, dict)
    )
    return TableFacts(
        name=t.get("name", fqn.rsplit(".", 1)[-1]),
        fqn=fqn,
        schema=_schema_of(fqn),
        description=_plain(t.get("description", "")),
        owners=owners,
        tier=tier,
        domain=domain,
        columns=tuple(
            ColumnFacts(
                name=c.get("name", ""),
                data_type=c.get("dataType", ""),
                description=_plain(c.get("description", "")),
            )
            for c in (t.get("columns") or [])
        ),
    )


def _schema_of(fqn: str) -> str:
    """`service.database.schema.tabla` → `schema`."""
    parts = fqn.split(".")
    return parts[-2] if len(parts) >= 2 else "public"


def _plain(text: str) -> str:
    """Las descripciones de OM llegan en markdown/HTML; acá se quiere texto."""
    import re

    return re.sub(r"<[^>]+>", "", text or "").strip()


def from_env() -> OpenMetadataCatalog:
    """Construye el cliente desde el entorno. Nunca imprime la credencial.

    Si hay un `OPENMETADATA_TOKEN`, se comprueba antes de confiar en él y se
    cae a email/password cuando no sirve. Suena a exceso de cuidado y salió de
    un fallo real: un token de otra instancia vive en el vault, y cargar el
    vault para tomar una clave de LLM lo metía en el entorno sin querer. Como
    el token tenía precedencia, todas las consultas daban 401 y el síntoma
    aparecía a tres capas de distancia — un agente que "no consultó el
    catálogo".
    """
    base = os.getenv("OPENMETADATA_URL")
    if not base:
        raise OpenMetadataError("falta OPENMETADATA_URL")
    token = os.getenv("OPENMETADATA_TOKEN") or None
    email = os.getenv("OPENMETADATA_EMAIL") or None
    password = os.getenv("OPENMETADATA_PASSWORD") or None

    if token:
        candidate = OpenMetadataCatalog(base, token=token)
        try:
            # Tiene que ser un endpoint que EXIJA autenticación. `/system/version`
            # responde 200 sin credencial, así que validar contra él da por bueno
            # cualquier token — que fue exactamente lo que pasó la primera vez.
            candidate._get("/glossaryTerms", {"limit": 1})
            return candidate
        except OpenMetadataError:
            candidate.close()
            if not (email and password):
                raise OpenMetadataError(
                    "OPENMETADATA_TOKEN no sirve contra esta instancia y no hay "
                    "email/password para reemplazarlo"
                ) from None

    return OpenMetadataCatalog(base, email=email, password=password)

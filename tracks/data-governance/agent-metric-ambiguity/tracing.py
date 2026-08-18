"""Grabador de llamadas a herramientas.

El trace es la evidencia central del POC: sin él, "el agente consultó el
catálogo antes de tocar los datos" es una afirmación del agente sobre sí mismo.
Con él, es algo que un tercero verifica leyendo un archivo.

Dos decisiones que valen la pena:

- **El trace se graba, no se narra.** Lo escribe el envoltorio que ejecuta la
  herramienta, no el modelo. Un modelo que reporta sus propios pasos puede
  omitir uno; un envoltorio no tiene cómo.
- **Se sanea al grabar, no al publicar.** Si el saneado fuera un paso posterior,
  la versión sucia existiría en disco aunque sea un rato, y el archivo que se
  commitea saldría de la memoria de alguien.

Sin dependencias de terceros: la CI lo importa con `uvx pytest`.
"""

from __future__ import annotations

import json
import re
from typing import Any

#: Fases del recorrido. El orden importa y el orquestador lo hace cumplir.
PHASE_METADATA = "metadata"
PHASE_SQL = "sql"

#: Nombres de parámetro cuyo valor no se graba nunca, aunque venga vacío.
_SENSITIVE_KEYS = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|bearer|credential)",
    re.IGNORECASE,
)

#: Formas de secreto que pueden colarse dentro de un valor de texto — por
#: ejemplo una URL con credenciales embebidas o un JWT en un mensaje de error.
_SECRET_SHAPES = [
    (re.compile(r"(?i)\b(postgres(?:ql)?|mysql|mongodb)://[^\s:@/]+:[^\s@]+@"), r"\1://***:***@"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"), "***jwt***"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/-]{16,}=*"), r"\1 ***"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "***api-key***"),
]

REDACTED = "***"


def sanitize(value: Any, *, _depth: int = 0) -> Any:
    """Devuelve una copia del valor sin secretos.

    Recorre diccionarios y listas. Un valor cuya *clave* parezca sensible se
    reemplaza entero; los textos además se revisan por si traen un secreto
    embebido aunque la clave sea inocente.
    """
    if _depth > 12:
        return "***profundidad-excedida***"
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(k, str) and _SENSITIVE_KEYS.search(k):
                out[k] = REDACTED
            else:
                out[k] = sanitize(v, _depth=_depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [sanitize(v, _depth=_depth + 1) for v in value]
    if isinstance(value, str):
        out = value
        for pattern, replacement in _SECRET_SHAPES:
            out = pattern.sub(replacement, out)
        return out
    return value


class Trace:
    """Lista ordenada de llamadas, con la fase en la que ocurrió cada una."""

    def __init__(self, question: str, *, mode: str) -> None:
        self.question = question
        self.mode = mode
        self.steps: list[dict[str, Any]] = []

    def record(
        self,
        *,
        phase: str,
        tool: str,
        args: dict[str, Any] | None = None,
        ok: bool = True,
        summary: str = "",
        detail: Any = None,
    ) -> dict[str, Any]:
        step = {
            "seq": len(self.steps) + 1,
            "phase": phase,
            "tool": tool,
            "args": sanitize(args or {}),
            "ok": ok,
            "summary": sanitize(summary),
        }
        if detail is not None:
            step["detail"] = sanitize(detail)
        self.steps.append(step)
        return step

    # -- lecturas que usan los tests y el informe --------------------------

    def tools_in_order(self) -> list[str]:
        return [s["tool"] for s in self.steps]

    def phases_in_order(self) -> list[str]:
        return [s["phase"] for s in self.steps]

    def first_index_of_phase(self, phase: str) -> int:
        for i, s in enumerate(self.steps):
            if s["phase"] == phase:
                return i
        return -1

    def metadata_precedes_sql(self) -> bool:
        """¿Hubo al menos una consulta de metadata y ninguna de SQL antes?

        Con cero llamadas de SQL la respuesta es `True` de forma trivial, pero
        también es cierta: no se tocó el dato. Con cero llamadas de metadata es
        `False`, que es el caso que interesa detectar.
        """
        first_meta = self.first_index_of_phase(PHASE_METADATA)
        first_sql = self.first_index_of_phase(PHASE_SQL)
        if first_meta == -1:
            return False
        if first_sql == -1:
            return True
        return first_meta < first_sql

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "mode": self.mode,
            "steps": self.steps,
            "invariants": {
                "metadata_before_sql": self.metadata_precedes_sql(),
                "metadata_calls": sum(1 for s in self.steps if s["phase"] == PHASE_METADATA),
                "sql_calls": sum(1 for s in self.steps if s["phase"] == PHASE_SQL),
            },
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=False)

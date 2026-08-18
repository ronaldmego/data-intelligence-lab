#!/usr/bin/env python3
"""Renderiza la corrida offline como imagen de terminal.

    python render_evidence.py

El binario no se edita a mano: se regenera desde la corrida. Si el resultado
cambia, la imagen cambia con él — que es la única forma de que una captura de
pantalla siga siendo evidencia y no un adorno que envejeció.

Corre siempre **offline**, contra la captura versionada, para que cualquiera
pueda regenerarla sin levantar servicios.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SALIDA = HERE / "evidencia" / "corrida.png"

FUENTES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
]

FONDO = (13, 17, 23)
TEXTO = (201, 209, 217)
TENUE = (110, 118, 129)
ACENTO = (121, 192, 255)
ALERTA = (255, 166, 87)
OK = (86, 211, 100)

MARGEN = 24
TAM = 15
INTERLINEA = 22
#: Ancho máximo. Sin esto, la consulta de unión estira el lienzo a más de 4 000
#: píxeles y el resto del informe queda ilegible al escalar la imagen: una sola
#: línea larga decide cómo se ve todo lo demás.
COLUMNAS = 116


def _fuente(tam: int) -> ImageFont.FreeTypeFont:
    for ruta in FUENTES:
        if Path(ruta).exists():
            return ImageFont.truetype(ruta, tam)
    raise SystemExit("no hay una fuente monoespaciada disponible")


def _color(linea: str) -> tuple[int, int, int]:
    limpia = linea.strip()
    if limpia.startswith("$"):
        return OK
    if limpia in {"OPCIONES — elegí según la decisión que tengas que tomar", "GOBIERNO",
                  "HECHOS", "INTERPRETACIÓN", "LÍMITES",
                  "CAMINOS ALTERNATIVOS (contraste de la definición de actividad)"}:
        return ACENTO
    if "AMBIGUA" in limpia or "NO señalan" in limpia or "no señalan" in limpia:
        return ALERTA
    if limpia.startswith(("responde:", "el catálogo dice:", "fuentes:", "SQL:")):
        return TENUE
    return TEXTO


def main() -> int:
    corrida = subprocess.run(
        [sys.executable, "run.py"], cwd=HERE, capture_output=True, text=True, check=True
    )
    crudas = ["$ python run.py", ""] + corrida.stdout.rstrip("\n").split("\n")
    lineas: list[str] = []
    for linea in crudas:
        if len(linea) <= COLUMNAS:
            lineas.append(linea)
            continue
        sangria = " " * (len(linea) - len(linea.lstrip()) + 4)
        envueltas = textwrap.wrap(
            linea, width=COLUMNAS, subsequent_indent=sangria,
            break_long_words=True, break_on_hyphens=False,
        )
        lineas.extend(envueltas or [linea])

    fuente = _fuente(TAM)
    ancho_car = fuente.getbbox("M")[2]
    ancho = MARGEN * 2 + ancho_car * max(len(x) for x in lineas)
    alto = MARGEN * 2 + INTERLINEA * len(lineas)

    img = Image.new("RGB", (ancho, alto), FONDO)
    dib = ImageDraw.Draw(img)
    for i, linea in enumerate(lineas):
        dib.text((MARGEN, MARGEN + i * INTERLINEA), linea, font=fuente, fill=_color(linea))

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    img.save(SALIDA)
    print(f"{SALIDA} · {ancho}x{alto} · {len(lineas)} líneas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

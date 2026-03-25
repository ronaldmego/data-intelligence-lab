#!/usr/bin/env python3
"""
DataGov Analyst - Visualization Module
Genera figuras matplotlib según el tipo de variable (data-to-viz.com).

Principios de Wilke (Fundamentals of Data Visualization):
- No distorsionar ejes (bar charts siempre desde 0)
- No gráficos 3D
- Paleta de colores accesible (colorblind-friendly)
- Maximizar data-ink ratio
- Títulos y labels en español
"""

import matplotlib
matplotlib.use("Agg")  # backend sin display, compatible con Streamlit

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from typing import Optional

# Paleta accesible (colorblind-friendly, basada en Wong 2011)
PALETTE = ["#0072B2", "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#D55E00", "#CC79A7", "#999999"]
PRIMARY = PALETTE[0]

# Estilo base
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 11,
})


def plot_histogram(
    values: list[float],
    col_name: str,
    bins: int = 20,
    title: Optional[str] = None,
) -> plt.Figure:
    """
    Histograma para variables numéricas continuas.
    Incluye líneas de media y mediana.

    Args:
        values: Lista de valores numéricos (sin nulos)
        col_name: Nombre de la columna
        bins: Número de bins
        title: Título opcional (por defecto "Distribución de {col_name}")
    """
    fig, ax = plt.subplots(figsize=(8, 4))

    arr = np.array([float(v) for v in values if v is not None])
    ax.hist(arr, bins=bins, color=PRIMARY, edgecolor="white", linewidth=0.5)

    mean_val = np.mean(arr)
    median_val = np.median(arr)
    ax.axvline(mean_val, color=PALETTE[1], linestyle="--", linewidth=1.5, label=f"Media: {mean_val:,.2f}")
    ax.axvline(median_val, color=PALETTE[2], linestyle="-.", linewidth=1.5, label=f"Mediana: {median_val:,.2f}")

    ax.set_xlabel(col_name)
    ax.set_ylabel("Frecuencia")
    ax.set_title(title or f"Distribución de {col_name}")
    ax.legend(fontsize=9)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))

    fig.tight_layout()
    return fig


def plot_bar_chart(
    categories: list[str],
    values: list[float],
    col_name: str,
    title: Optional[str] = None,
    max_categories: int = 20,
    show_pct: bool = True,
) -> plt.Figure:
    """
    Bar chart horizontal para variables categóricas.
    Ordenado de mayor a menor. Siempre desde 0 (principio de Wilke).

    Args:
        categories: Etiquetas de las categorías
        values: Frecuencias o conteos
        col_name: Nombre de la columna
        title: Título opcional
        max_categories: Límite de categorías a mostrar
        show_pct: Mostrar porcentaje en las barras
    """
    # Ordenar y truncar
    pairs = sorted(zip(values, categories), reverse=True)[:max_categories]
    vals, cats = zip(*pairs) if pairs else ([], [])

    fig, ax = plt.subplots(figsize=(8, max(3, len(cats) * 0.45)))

    colors = [PALETTE[i % len(PALETTE)] for i in range(len(cats))]
    bars = ax.barh(range(len(cats)), vals, color=colors)

    # Labels en las barras
    total = sum(values)
    for bar, val in zip(bars, vals):
        pct = val / total * 100 if total > 0 else 0
        label = f" {val:,} ({pct:.1f}%)" if show_pct else f" {val:,}"
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2,
                label, va="center", fontsize=9)

    ax.set_yticks(range(len(cats)))
    ax.set_yticklabels(cats, fontsize=10)
    ax.set_xlabel("Frecuencia")
    ax.set_title(title or f"Distribución de {col_name}")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.set_xlim(0, max(vals) * 1.2 if vals else 1)  # espacio para labels

    if len(categories) > max_categories:
        ax.set_title((title or f"Distribución de {col_name}") + f" (top {max_categories})")

    fig.tight_layout()
    return fig


def plot_line_chart(
    x_values: list,
    y_values: list[float],
    col_name: str,
    x_label: str = "Fecha",
    title: Optional[str] = None,
) -> plt.Figure:
    """
    Line chart para series temporales.

    Args:
        x_values: Eje X (fechas o labels)
        y_values: Valores numéricos
        col_name: Nombre de la métrica
        x_label: Label del eje X
        title: Título opcional
    """
    fig, ax = plt.subplots(figsize=(10, 4))

    ax.plot(range(len(x_values)), y_values, color=PRIMARY, linewidth=2, marker="o", markersize=3)
    ax.fill_between(range(len(x_values)), y_values, alpha=0.1, color=PRIMARY)

    # Ticks del eje X — mostrar máximo 12 para no saturar
    step = max(1, len(x_values) // 12)
    ax.set_xticks(range(0, len(x_values), step))
    ax.set_xticklabels([str(x_values[i]) for i in range(0, len(x_values), step)],
                       rotation=30, ha="right", fontsize=9)

    ax.set_xlabel(x_label)
    ax.set_ylabel(col_name)
    ax.set_title(title or f"Evolución de {col_name}")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    fig.tight_layout()
    return fig


def plot_boxplot(
    data: dict[str, list[float]],
    col_name: str,
    group_col: Optional[str] = None,
    title: Optional[str] = None,
) -> plt.Figure:
    """
    Boxplot para numérica + categórica (distribución por grupo).
    Si data tiene 1 clave, muestra boxplot simple.

    Args:
        data: Dict {grupo: [valores]}. Para boxplot simple: {"": [valores]}
        col_name: Nombre de la columna numérica
        group_col: Nombre de la columna de agrupación (para el label)
        title: Título opcional
    """
    groups = list(data.keys())
    values = [data[g] for g in groups]

    fig, ax = plt.subplots(figsize=(max(5, len(groups) * 1.2), 5))

    bp = ax.boxplot(values, patch_artist=True, notch=False,
                    medianprops=dict(color="white", linewidth=2))

    for patch, color in zip(bp["boxes"], [PALETTE[i % len(PALETTE)] for i in range(len(groups))]):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax.set_xticks(range(1, len(groups) + 1))
    ax.set_xticklabels(groups, rotation=20 if len(groups) > 4 else 0, ha="right")
    ax.set_ylabel(col_name)
    if group_col:
        ax.set_xlabel(group_col)

    title_str = title or (f"{col_name} por {group_col}" if group_col else f"Distribución de {col_name}")
    ax.set_title(title_str)

    fig.tight_layout()
    return fig


def parse_viz_request(response_text: str) -> Optional[dict]:
    """
    Detectar si el agente incluyó una solicitud de visualización en su respuesta.
    El agente puede señalar un gráfico con un bloque especial:

    ```viz
    type: bar_chart
    col_name: status
    categories: active,inactive,pending
    values: 6500,2200,1300
    title: Distribución de status
    ```

    Returns:
        Dict con los parámetros del gráfico, o None si no hay bloque viz.
    """
    import re
    match = re.search(r"```viz\s*(.*?)```", response_text, re.DOTALL)
    if not match:
        return None

    params = {}
    for line in match.group(1).strip().split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            params[key.strip()] = val.strip()

    if "type" not in params:
        return None

    return params


def render_viz(params: dict) -> Optional[plt.Figure]:
    """
    Renderizar un gráfico a partir de los parámetros parseados por parse_viz_request.

    Returns:
        Figura matplotlib o None si los parámetros son inválidos.
    """
    viz_type = params.get("type", "")
    col_name = params.get("col_name", "valor")
    title = params.get("title")

    try:
        if viz_type == "bar_chart":
            cats = [c.strip() for c in params.get("categories", "").split(",")]
            vals = [float(v.strip()) for v in params.get("values", "").split(",")]
            if cats and vals and len(cats) == len(vals):
                return plot_bar_chart(cats, vals, col_name, title=title)

        elif viz_type == "histogram":
            vals = [float(v.strip()) for v in params.get("values", "").split(",")]
            if vals:
                return plot_histogram(vals, col_name, title=title)

        elif viz_type == "line_chart":
            x_vals = [x.strip() for x in params.get("x_values", "").split(",")]
            y_vals = [float(v.strip()) for v in params.get("y_values", "").split(",")]
            x_label = params.get("x_label", "Fecha")
            if x_vals and y_vals and len(x_vals) == len(y_vals):
                return plot_line_chart(x_vals, y_vals, col_name, x_label=x_label, title=title)

        elif viz_type == "boxplot":
            # Formato simple: una sola distribución
            vals = [float(v.strip()) for v in params.get("values", "").split(",")]
            if vals:
                return plot_boxplot({"": vals}, col_name, title=title)

    except (ValueError, TypeError):
        return None

    return None

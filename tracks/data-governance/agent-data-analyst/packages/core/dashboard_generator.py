"""
Khipu Dashboard Generator
Genera dashboard HTML interactivo con resultados de Auto-EDA
"""
import json
from typing import Dict, List, Any, Optional
from datetime import datetime


class DashboardGenerator:
    """Genera dashboards HTML a partir de resultados de Auto-EDA"""
    
    CHART_COLORS = [
        '#3b82f6',  # blue
        '#10b981',  # green
        '#f59e0b',  # amber
        '#ef4444',  # red
        '#8b5cf6',  # purple
        '#ec4899',  # pink
        '#06b6d4',  # cyan
        '#84cc16',  # lime
    ]
    
    def __init__(self):
        self.charts_data = []
    
    def generate_html(
        self,
        schema_name: str,
        tables_analysis: List[Dict],
        summary: Dict,
        generated_at: Optional[str] = None
    ) -> str:
        """
        Genera un dashboard HTML completo con Chart.js
        
        Args:
            schema_name: Nombre del schema analizado
            tables_analysis: Lista de análisis por tabla
            summary: Resumen general del schema
            generated_at: Timestamp de generación
        
        Returns:
            HTML string del dashboard
        """
        if not generated_at:
            generated_at = datetime.now().isoformat()
        
        # Construir secciones de tablas
        tables_html = ""
        charts_js = []
        chart_idx = 0
        
        for table in tables_analysis:
            table_name = table.get('table', 'unknown')
            columns = table.get('columns_analysis', [])
            stats = table.get('statistics', {})
            
            # Cards de estadísticas por tabla
            stats_cards = self._generate_stats_cards(table_name, stats)
            
            # Charts por columna
            columns_charts = ""
            for col in columns:
                col_name = col.get('name')
                col_type = col.get('inferred_type')
                viz_type = col.get('suggested_viz', 'table')
                col_stats = col.get('stats', {})
                
                if col_stats:
                    chart_id = f"chart_{chart_idx}"
                    chart_html, chart_js = self._generate_chart(
                        chart_id, col_name, col_type, viz_type, col_stats
                    )
                    columns_charts += chart_html
                    if chart_js:
                        charts_js.append(chart_js)
                    chart_idx += 1
            
            tables_html += f"""
            <section class="table-section" id="table-{table_name}">
                <h2 class="table-title">
                    <span class="table-icon">📊</span> {table_name}
                </h2>
                <p class="table-desc">{table.get('description', 'Sin descripción')}</p>
                
                <div class="stats-row">
                    {stats_cards}
                </div>
                
                <div class="charts-grid">
                    {columns_charts}
                </div>
            </section>
            """
        
        # Resumen general
        summary_html = self._generate_summary_section(schema_name, summary, tables_analysis)
        
        # Combinar JS de charts
        all_charts_js = "\n".join(charts_js)
        
        return self._generate_full_html(
            schema_name, summary_html, tables_html, all_charts_js, generated_at
        )
    
    def _generate_stats_cards(self, table_name: str, stats: Dict) -> str:
        """Genera cards de estadísticas para una tabla"""
        cards = []
        
        if 'row_count' in stats:
            cards.append(self._stat_card("Filas", f"{stats['row_count']:,}", "📝"))
        if 'column_count' in stats:
            cards.append(self._stat_card("Columnas", stats['column_count'], "📋"))
        if 'null_percent_avg' in stats:
            cards.append(self._stat_card("% Nulos (avg)", f"{stats['null_percent_avg']:.1f}%", "⚠️"))
        if 'size_category' in stats:
            icons = {'small': '🟢', 'medium': '🟡', 'large': '🟠', 'huge': '🔴'}
            cards.append(self._stat_card("Tamaño", stats['size_category'], icons.get(stats['size_category'], '⚪')))
        
        return "".join(cards)
    
    def _stat_card(self, label: str, value: Any, icon: str) -> str:
        return f"""
        <div class="stat-card">
            <span class="stat-icon">{icon}</span>
            <div class="stat-content">
                <span class="stat-value">{value}</span>
                <span class="stat-label">{label}</span>
            </div>
        </div>
        """
    
    def _generate_chart(
        self,
        chart_id: str,
        col_name: str,
        col_type: str,
        viz_type: str,
        stats: Dict
    ) -> tuple:
        """Genera HTML y JS para un chart"""
        
        # Para histogramas y barras
        if viz_type in ['histogram', 'bar_chart', 'horizontal_bar', 'top_n_bar']:
            if 'distribution' in stats:
                data = stats['distribution']
                labels = [str(d.get('label', d.get('value', ''))) for d in data]
                values = [d.get('count', d.get('frequency', 0)) for d in data]
                
                html = f"""
                <div class="chart-container">
                    <h4 class="chart-title">{col_name}</h4>
                    <span class="chart-type-badge">{col_type}</span>
                    <canvas id="{chart_id}"></canvas>
                </div>
                """
                
                chart_type = 'bar'
                if viz_type == 'horizontal_bar':
                    chart_type = 'bar'
                    options = "indexAxis: 'y',"
                else:
                    options = ""
                
                js = f"""
                new Chart(document.getElementById('{chart_id}'), {{
                    type: '{chart_type}',
                    data: {{
                        labels: {json.dumps(labels)},
                        datasets: [{{
                            label: '{col_name}',
                            data: {json.dumps(values)},
                            backgroundColor: '{self.CHART_COLORS[0]}',
                            borderColor: '{self.CHART_COLORS[0]}',
                            borderWidth: 1
                        }}]
                    }},
                    options: {{
                        {options}
                        responsive: true,
                        plugins: {{
                            legend: {{ display: false }}
                        }},
                        scales: {{
                            y: {{ beginAtZero: true }}
                        }}
                    }}
                }});
                """
                return html, js
        
        # Para stats numéricas sin distribución
        if col_type == 'numeric' and 'min' in stats:
            html = f"""
            <div class="chart-container stats-only">
                <h4 class="chart-title">{col_name}</h4>
                <span class="chart-type-badge">{col_type}</span>
                <div class="numeric-stats">
                    <div class="stat-item"><span class="stat-key">Min:</span> {stats.get('min', 'N/A')}</div>
                    <div class="stat-item"><span class="stat-key">Max:</span> {stats.get('max', 'N/A')}</div>
                    <div class="stat-item"><span class="stat-key">Avg:</span> {stats.get('avg', 'N/A')}</div>
                    <div class="stat-item"><span class="stat-key">Distinct:</span> {stats.get('distinct', 'N/A')}</div>
                    <div class="stat-item"><span class="stat-key">Nulls:</span> {stats.get('null_percent', 0):.1f}%</div>
                </div>
            </div>
            """
            return html, ""
        
        # Fallback: mostrar stats básicas
        html = f"""
        <div class="chart-container stats-only">
            <h4 class="chart-title">{col_name}</h4>
            <span class="chart-type-badge">{col_type}</span>
            <div class="numeric-stats">
                <div class="stat-item"><span class="stat-key">Distinct:</span> {stats.get('distinct', 'N/A')}</div>
                <div class="stat-item"><span class="stat-key">Nulls:</span> {stats.get('null_percent', 0):.1f}%</div>
            </div>
        </div>
        """
        return html, ""
    
    def _generate_summary_section(
        self,
        schema_name: str,
        summary: Dict,
        tables: List[Dict]
    ) -> str:
        """Genera sección de resumen del schema"""
        total_rows = sum(t.get('statistics', {}).get('row_count', 0) for t in tables)
        total_cols = sum(t.get('statistics', {}).get('column_count', 0) for t in tables)
        
        table_links = "".join([
            f'<a href="#table-{t["table"]}" class="table-link">{t["table"]}</a>'
            for t in tables
        ])
        
        return f"""
        <section class="summary-section">
            <h1>🔍 Auto-EDA: {schema_name}</h1>
            <p class="summary-desc">Análisis exploratorio automático generado por Khipu</p>
            
            <div class="summary-stats">
                <div class="summary-stat">
                    <span class="summary-value">{len(tables)}</span>
                    <span class="summary-label">Tablas</span>
                </div>
                <div class="summary-stat">
                    <span class="summary-value">{total_cols}</span>
                    <span class="summary-label">Columnas</span>
                </div>
                <div class="summary-stat">
                    <span class="summary-value">{total_rows:,}</span>
                    <span class="summary-label">Registros</span>
                </div>
            </div>
            
            <div class="table-nav">
                <strong>Tablas:</strong> {table_links}
            </div>
        </section>
        """
    
    def _generate_full_html(
        self,
        schema_name: str,
        summary_html: str,
        tables_html: str,
        charts_js: str,
        generated_at: str
    ) -> str:
        """Genera el HTML completo del dashboard"""
        return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Khipu Auto-EDA - {schema_name}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --primary: #3b82f6;
            --primary-dark: #2563eb;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text: #1e293b;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
        }}
        
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }}
        
        /* Summary Section */
        .summary-section {{
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 3rem;
            border-radius: 16px;
            margin-bottom: 2rem;
        }}
        
        .summary-section h1 {{
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }}
        
        .summary-desc {{
            opacity: 0.9;
            font-size: 1.1rem;
            margin-bottom: 2rem;
        }}
        
        .summary-stats {{
            display: flex;
            gap: 2rem;
            margin-bottom: 1.5rem;
        }}
        
        .summary-stat {{
            text-align: center;
        }}
        
        .summary-value {{
            display: block;
            font-size: 2.5rem;
            font-weight: 700;
        }}
        
        .summary-label {{
            font-size: 0.9rem;
            opacity: 0.8;
        }}
        
        .table-nav {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            align-items: center;
        }}
        
        .table-link {{
            background: rgba(255,255,255,0.2);
            color: white;
            padding: 0.4rem 0.8rem;
            border-radius: 20px;
            text-decoration: none;
            font-size: 0.85rem;
            transition: background 0.2s;
        }}
        
        .table-link:hover {{
            background: rgba(255,255,255,0.3);
        }}
        
        /* Table Sections */
        .table-section {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 2rem;
            margin-bottom: 2rem;
            border: 1px solid var(--border);
        }}
        
        .table-title {{
            font-size: 1.5rem;
            color: var(--text);
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        
        .table-icon {{
            font-size: 1.2rem;
        }}
        
        .table-desc {{
            color: var(--text-muted);
            margin-bottom: 1.5rem;
        }}
        
        /* Stats Row */
        .stats-row {{
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
            margin-bottom: 2rem;
        }}
        
        .stat-card {{
            background: var(--bg);
            padding: 1rem 1.5rem;
            border-radius: 8px;
            display: flex;
            align-items: center;
            gap: 0.75rem;
            min-width: 140px;
        }}
        
        .stat-icon {{
            font-size: 1.5rem;
        }}
        
        .stat-content {{
            display: flex;
            flex-direction: column;
        }}
        
        .stat-value {{
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--text);
        }}
        
        .stat-label {{
            font-size: 0.8rem;
            color: var(--text-muted);
        }}
        
        /* Charts Grid */
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 1.5rem;
        }}
        
        .chart-container {{
            background: var(--bg);
            padding: 1.5rem;
            border-radius: 8px;
            position: relative;
        }}
        
        .chart-title {{
            font-size: 1rem;
            margin-bottom: 0.5rem;
            color: var(--text);
        }}
        
        .chart-type-badge {{
            position: absolute;
            top: 1rem;
            right: 1rem;
            background: var(--primary);
            color: white;
            padding: 0.2rem 0.6rem;
            border-radius: 4px;
            font-size: 0.7rem;
            text-transform: uppercase;
        }}
        
        .stats-only {{
            min-height: 150px;
        }}
        
        .numeric-stats {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 0.75rem;
            margin-top: 1rem;
        }}
        
        .stat-item {{
            font-size: 0.9rem;
        }}
        
        .stat-key {{
            font-weight: 600;
            color: var(--text-muted);
        }}
        
        /* Footer */
        .footer {{
            text-align: center;
            padding: 2rem;
            color: var(--text-muted);
            font-size: 0.85rem;
        }}
        
        .footer a {{
            color: var(--primary);
            text-decoration: none;
        }}
        
        /* Responsive */
        @media (max-width: 768px) {{
            .container {{ padding: 1rem; }}
            .summary-section {{ padding: 1.5rem; }}
            .summary-section h1 {{ font-size: 1.75rem; }}
            .summary-stats {{ flex-direction: column; gap: 1rem; }}
            .charts-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        {summary_html}
        {tables_html}
        
        <footer class="footer">
            <p>Generado por <strong>Khipu Enterprise</strong> - {generated_at}</p>
            <p><a href="https://github.com/galacticaia/khipu">GalacticaIA</a></p>
        </footer>
    </div>
    
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            {charts_js}
        }});
    </script>
</body>
</html>
"""

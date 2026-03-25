# DataGov Analyst 📊

> Super Analista de Datos con IA — entiende tus datos antes de analizarlos.

**Private repository** - [GalacticaIA](https://galacticaia.com)

## Qué es

DataGov Analyst es un agente conversacional que combina:
- **OpenMetadata** (catálogo de datos gobernado) — sabe qué datos existen y cómo están organizados
- **SQL directo** — puede ejecutar queries para explorar los datos reales
- **Visualización inteligente** — elige el gráfico correcto según el tipo de dato

## Filosofía

**Analista descriptivo.** Entiende datos, describe distribuciones, detecta problemas de calidad y genera gráficos informativos. No hace predicciones ni modelos.

## Stack

- **UI**: Streamlit
- **LLM**: Google Gemini 2.5 Pro
- **Catálogo**: OpenMetadata (via MCP)
- **SQL**: PostgreSQL/Supabase (via MCP)
- **Viz**: matplotlib + seaborn

## Quick Start

```bash
cp .env.example .env
# Editar .env con credenciales
pip install -r requirements.txt
streamlit run app.py --server.port 4005
```

## Roadmap

Ver [ROADMAP.md](./ROADMAP.md)

## Basado en

Evolución de [openmetadata-mcp-client](https://github.com/ronaldmego/openmetadata-agent) — patrón probado de agente conversacional con MCP.

## License

Proprietary - GalacticaIA

# Khipu Analytics - Super Analista de Datos con IA

## Tabla de Contenidos

- [Puerto](#puerto)
- [Visión y Filosofía](#visión-y-filosofía)
- [Arquitectura](#arquitectura)
- [Quick Start](#quick-start)
- [Configuración](#configuración)
- [Comandos Frecuentes](#comandos-frecuentes)
- [Filosofía de Desarrollo](#filosofía-de-desarrollo)
- [Boris Dev Principles](#boris-dev-principles)
- [Skills Relevantes](#skills-relevantes)
- [Referencias Teóricas](#referencias-teóricas)
- [Deploy](#deploy)
- [Seguridad](#seguridad)

---

## Puerto

| Item | Valor |
|------|-------|
| Puerto Prod | `4005` (Tailscale only) |
| Bind | `<vps-host>` |
| URL | http://<vps-host>:4005 |
| Proceso | `streamlit run app.py` |

---

## Visión y Filosofía

**Un Super Analista de Datos que primero ENTIENDE antes de opinar.**

Khipu Analytics es un agente conversacional que combina:
1. **Conocimiento del catálogo** (OpenMetadata MCP) — qué datos existen, cómo están gobernados, documentados, con linaje
2. **Capacidad de exploración** (SQL MCP) — ejecutar queries para describir los datos reales

### Principios Fundamentales

1. **Descriptivo y nada más** — Este agente describe datos, no predice ni modela
2. **Entender antes de opinar** — Perfil → calidad → distribuciones → insights
3. **Visualización correcta** — Seguir data-to-viz.com, no gráficos al azar
4. **Insights con fundamento** — Cada observación tiene base en los datos reales

### Arquitectura MCP Plug & Play

El agente es un **cerebro** que conecta a **MCPs como plugins**. No tiene herramientas hardcodeadas.

```
agent.py (cerebro + Gemini)
├── register_mcp("openmetadata", server)  ← catálogo gobernado
├── register_mcp("sql", server)           ← queries directas
├── register_mcp("snowflake", ...)        ← futuro, 1 línea
└── register_mcp("bigquery", ...)         ← futuro, 1 línea
```

**Principio:** Como OpenClaw con skills. El cerebro no tiene las herramientas en su código.
Las descubre automáticamente, las registra, y las usa via protocolo MCP.
Agregar un nuevo "brazo" = crear el MCP server + una línea `register_mcp()`.

**Cada MCP es independiente:** tiene su propia conexión, sus propios tools, y se puede
reemplazar o actualizar sin tocar el cerebro ni los otros MCPs.

### Estrategia de uso de MCPs

El agente tiene acceso a múltiples MCPs que pueden tener información similar.
La orientación es:

1. **OpenMetadata primero para contexto** — Entender qué datos existen, cómo están
   gobernados, documentados, con linaje y glosario de negocio. OpenMetadata da la
   visión unificada e independiente del motor de base de datos.
2. **SQL para exploración profunda** — Una vez que sabe qué hay, usar SQL para
   obtener estadísticas reales, distribuciones, valores concretos.
3. **Combinar ambos** — El análisis más valioso viene de cruzar: contexto de
   gobernanza (OpenMetadata) + datos reales (SQL).

El agente NO está obligado a seguir un orden rígido, pero el prompt le da esta
orientación como best practice.

### Anti-patrones (NO hacer)

- ❌ Clustering, segmentación, churn, predicciones, ML — fuera de alcance
- ❌ Análisis inferencial (tests estadísticos, p-values, intervalos de confianza)
- ❌ Gráficos decorativos sin propósito
- ❌ Análisis sin entender primero qué datos hay
- ❌ Reinventar la rueda — usar librerías probadas
- ❌ Ignorar OpenMetadata cuando tiene información relevante (descripción, tags, linaje)

---

## Arquitectura

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Streamlit     │────▶│   Agent         │────▶│  OpenMetadata   │
│   Chat UI       │     │   (Gemini LLM)  │     │  REST API       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │
        │                       ├──────────────▶┌─────────────────┐
        │                       │               │  PostgreSQL/    │
        ▼                       ▼               │  Supabase (SQL) │
   Usuario              MCP Tools:              └─────────────────┘
   (browser)            ├── OpenMetadata MCP
                        │   - search_catalog
                        │   - list_tables
                        │   - get_table_details
                        │   - get_lineage
                        │   - list_databases
                        │   - list_glossary_terms
                        │
                        └── SQL MCP (Fase 1.2)
                            - execute_query
                            - describe_table
                            - get_column_stats
                            - get_distribution
```

### Estructura del Proyecto

```
khipu-analytics/
├── app.py              # Streamlit UI (chat + visualizaciones)
├── server.py           # OpenMetadata MCP tools
├── sql_server.py       # SQL MCP tools (Fase 1.2)
├── viz.py              # Módulo de visualización (matplotlib)
├── classifier.py       # Clasificador de tipos de variables
├── .env                # Configuración local (no commitear)
├── .env.example        # Template de configuración
├── requirements.txt    # Dependencias Python
├── CLAUDE.md           # Este archivo — visión y estándares (gitignored)
├── ROADMAP.md          # Roadmap progresivo con subfases
├── ARCHITECTURE.md     # Diseño del sistema y flujo de datos
├── KNOWN_ISSUES.md     # Limitaciones conocidas y workarounds
└── README.md           # Documentación pública
```

---

## Quick Start

```bash
cd ~/projects/khipu-analytics

# Configurar
cp .env.example .env
# Editar .env con credenciales

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar
streamlit run app.py --server.port 4005

# Acceder: http://<vps-host>:4005
```

---

## Configuración

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `GOOGLE_API_KEY` | API key de Gemini (pagada recomendada) | `AIzaSy...` |
| `OPENMETADATA_URL` | URL de la instancia OpenMetadata | `http://<vps-host>:8585` |
| `OPENMETADATA_TOKEN` | JWT token de bot de OpenMetadata | `eyJhbG...` |
| `GEMINI_MODEL` | Modelo a usar | `gemini-2.5-pro` |
| `DATABASE_URL` | Conexión PostgreSQL/Supabase (Fase 1.2) | `postgresql://...` |

---

## Comandos Frecuentes

```bash
# --- Desarrollo ---
streamlit run app.py --server.port 4005
streamlit run app.py --server.port 4005 --server.address <vps-host>

# --- Testing ---
python test_connection.py
python -c "from server import list_tables; print(list_tables())"

# --- Dependencias ---
pip install -r requirements.txt
```

---

## Filosofía de Desarrollo

### Stack

- **UI**: Streamlit (chat + matplotlib inline)
- **LLM**: Google Gemini 2.5 Pro via `google-genai`
- **Catálogo**: OpenMetadata REST API (via MCP)
- **SQL**: PostgreSQL/Supabase (via MCP)
- **Visualización**: matplotlib + seaborn
- **Lenguaje**: Python 3.10+

### Convenciones

- **Idioma del código**: inglés (variables, funciones, clases)
- **Idioma de respuestas al usuario**: español
- **Naming**: snake_case para funciones, PascalCase para clases
- **Un archivo por responsabilidad**
- **Toda configuración en .env**, nunca hardcoded

### Patrón base (heredado de openmetadata-mcp-client)

- Tools MCP en `server.py` usando FastMCP
- Agente orquesta LLM + tools
- `app.py` solo capa de presentación
- Respuestas siempre en español

---

## Boris Dev Principles

### Non-Negotiable Directives

**Planning:**
- Plan antes de cualquier tarea multi-paso (3+ pasos o decisiones arquitectónicas). Escribir en `tasks/todo.md`.
- Si algo falla, STOP y re-planificar. No seguir empujando un enfoque que falla.

**Quality:**
- Probar que el trabajo está hecho — tests, logs, o screenshots. Nunca decir "funciona" sin evidencia.
- Resolver bugs autónomamente — leer logs, encontrar causa raíz, arreglar. Sin hand-holding.
- Después de CUALQUIER corrección del usuario, actualizar `tasks/lessons.md` inmediatamente.
- Revisar `tasks/lessons.md` al inicio de sesión. Nunca repetir un error documentado.

**Traceability:**
- Todo feature, fix o mejora empieza como GitHub Issue. Sin issue, sin trabajo.
- Actualizar `CHANGELOG.md` en cada cambio significativo. Referenciar el Issue (`#N`).
- Todo PR debe incluir `Closes #N` para auto-cerrar el issue al mergear.

**Skills (uso obligatorio):**
- Revisar `~/.claude/skills/` al inicio de sesión. Usar skills existentes.
- Invocar `supabase-local` antes de cualquier operación DDL en Supabase.
- Invocar `vps-admin` para permisos de servidor, redes Docker, operaciones sudo.
- Si una tarea se repite 3+ veces o tiene 3+ pasos, proponer nueva skill via GitHub Issue con label `global-standard`.

**Governance:**
- Puerto asignado o liberado → actualizar `~/.claude/port-registry.md`
- Proyecto creado, pausado o eliminado → actualizar `~/.claude/project-registry.md`

### Self-Check Questions

> **¿Es esta la mejor solución o solo la primera que funcionó?**
> ¿Lo escribiría así si 1000 personas van a leer el código?
> ¿El fix es quirúrgico o estoy aplicando duct tape?

> **¿Estoy usando bien mis recursos?**
> ¿Puedo delegar a un subagente para mantener el contexto limpio?
> ¿Estoy resolviendo demasiadas cosas a la vez? → Una tarea por subagente.

> **¿Hay una forma más simple?** Si la hay, ¿por qué no la uso?

> **¿Síntoma o causa?** Si apostara dinero a que esto no va a volver, ¿lo haría?

> **Antes de merge:**
> ¿Funciona, o solo no rompe? (No es lo mismo.)
> ¿Lo probé como usuario, no solo como desarrollador?
> ¿Si este cambio sale mal, puedo revertirlo limpiamente?

---

## Skills Relevantes

| Skill | Cuándo usar |
|-------|-------------|
| `supabase-local` | Antes de cualquier DDL en Supabase (schemas, tablas, RLS) |
| `vps-admin` | Permisos de servidor, redes Docker, operaciones sudo, health checks |
| `openmetadata-ops` | Operaciones sobre OpenMetadata REST API (tags, descripciones, ingestion) |

---

## Referencias Teóricas

### Visualización de Datos
- **data-to-viz.com** — Árbol de decisión para elegir el gráfico correcto:
  - 1 numérica → histogram, density plot
  - 2 numéricas (no ordenadas, pocos puntos) → scatter plot
  - 2 numéricas (ordenadas) → connected scatter, line chart
  - Categórica → bar chart, treemap
  - Numérica + Categórica → boxplot, violin plot
  - Series de tiempo → line chart, area chart
  - 3+ numéricas → heatmap, parallel coordinates

- **Claus Wilke — Fundamentals of Data Visualization** (clauswilke.com/dataviz):
  - Proporciones correctas (no distorsionar con 3D, truncar ejes, etc.)
  - Escala adecuada (log vs lineal)
  - Uso correcto del color
  - Principio de tinta-datos (maximizar info, minimizar decoración)

### Estadística Descriptiva
- Medidas de tendencia central: media, mediana, moda
- Medidas de dispersión: std, rango, IQR
- Distribuciones: normal, sesgada, bimodal
- Outliers: regla 1.5*IQR o 3σ

---

## Deploy

### Requisitos
- Python 3.10+
- OpenMetadata (URL + token)
- PostgreSQL/Supabase (connection string)
- API key Gemini
- Puerto 4005

### Pasos
1. Clonar proyecto
2. Configurar `.env`
3. `pip install -r requirements.txt`
4. `streamlit run app.py --server.port 4005`

---

## Seguridad

- **Credenciales**: siempre en `.env`, nunca en código
- **Acceso**: restringir por Tailscale
- **Tokens**: rotar periódicamente
- **SQL**: READ-ONLY para el agente (nunca INSERT/UPDATE/DELETE)
- **Puerto**: `4005` registrado en port-registry

---

## Proyecto Base

Este proyecto evolucionó desde `openmetadata-mcp-client` (agente conversacional para OpenMetadata). El patrón Streamlit + Gemini + FastMCP está probado y funciona.

Repositorio: https://github.com/ronaldmego/khipu-analytics

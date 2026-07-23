# Quick Finance Test

Plan corto para validar que el agente responde bien sobre la capa financiera del demo telco — issue base [galacticaia-gov#98](https://github.com/GalacticaIA/galacticaia-gov/issues/98), validación con CFO consultor en [galacticaia-gov#102](https://github.com/GalacticaIA/galacticaia-gov/issues/102).

## Pre-requisitos

- Streamlit corriendo en http://<vps-host>:4005
- Sidebar muestra:
  - `OpenMetadata: http://<vps-host>:8592`
  - `openmetadata (7 tools)` ✅ (incluye `list_glossaries` agregado en #29)
  - `sql (5 tools)` ✅
  - `Provider: Gemini` · `Modelo: gemini-2.5-pro`
- Schema `telco_demo` con 17 tablas (6 originales + 6 financieras + 5 de costos/P&L)
- Glosario `TelcoLATAM` con jerarquía `Marketing` / `Finanzas` / `Operacion`

## Datos esperados (snapshot Postgres, validación previa)

| Tabla | Filas |
|---|---:|
| customers | 100 |
| invoices | 281 |
| payments | 229 |
| accounts_receivable | 4,401 (45 clientes × ~daily snapshots) |
| chargebacks | 99 |
| arpu_monthly | 24 |
| revenue_daily | 720 |
| pl_monthly | 7 |

Si los conteos cambian por re-ingesta, ajustar expectativas de los tests.

## Comportamiento UX esperado (post-fixes #27, #28, #30, #33)

Antes de evaluar el contenido, validar la **forma**:

| Aspecto | Esperado |
|---|---|
| **Persona** | "Soy DataGov Analyst, agente de gobierno de datos." (una línea, sobria, sin "Super Analista", sin exclamaciones) |
| **Saludo** | Solo en el primer turno. En follow-ups arranca directo con la respuesta |
| **Tools** | Sidebar muestra `openmetadata (7)` + `sql (5)`. Si hay 6+5 = arquitectura vieja, falta `list_glossaries` |
| **Hallazgos** | Datos reales — nunca inventa customer_ids como `CUST-XXXX`. El formato real es `C000001`–`C000100` |
| **Snapshot tables** | Para `accounts_receivable` filtra al `MAX(snapshot_date)` por defecto |

## Tests

Ejecutar uno por uno y validar contra los criterios. Las cifras esperadas son contra la BD actual; pueden variar ±1% por simulación diaria.

### 1. Catálogo: glosario jerárquico

> ¿Qué glosarios y términos hay disponibles? Muestra la jerarquía.

**Validar:**
- Identifica el glosario raíz como `TelcoLATAM` (NO inventa "Glosario de Negocio" ni similares)
- Reconoce los 3 parent terms: `Marketing` (3 hijos), `Finanzas` (8 hijos), `Operacion` (3 hijos)
- Muestra los 17 términos anidados, no como lista plana
- Lista los 8 hijos de Finanzas: ARPU, MRR, Invoice, Payment, AccountsReceivable, Chargeback, Revenue, Recharge

### 2. Perfil de tabla (catálogo + SQL)

> Perfila la tabla invoices de telco_demo: estructura, calidad de datos y distribución por status.

**Validar:**
- Trae descripción y FQN desde OpenMetadata: `Supabase-TelcoDemo.postgres.telco_demo.invoices`
- 281 filas, 12 columnas, 0% nulos en cada columna
- Distribución de `status`: `paid` ~72.9% (205) · `issued` ~15.7% (44) · `overdue` ~11.4% (32)
- Marca con 🔴 outliers en `base_amount` y `total_amount` (max ~$99K-$107K vs avg ~$2K)

### 3. Pregunta de negocio (ARPU por segmento)

> ¿Cuál es el ARPU promedio por segmento de cliente en el último mes disponible?

**Validar:**
- Detecta `arpu_monthly` (24 filas) y filtra al último mes (`2026-04-01`)
- Devuelve los 4 segmentos con sus ARPUs:
  - `standard` $7,514.92
  - `basic` $6,789.15
  - `premium` $4,891.01
  - `enterprise` $4,825.42
- Bonus: nota la observación contraintuitiva (premium/enterprise menores que standard/basic) — efecto de outliers DQ no filtrados en `arpu_monthly`
- ⚠️ La tabla `arpu_monthly` está sucia (no filtra outliers). Para ARPU limpio recalcular desde `recharges + payments` con filtros DQ — ver `DEMO-FINANCIAL-CONSULTOR.md` sección 7.2

### 4. Cuentas por cobrar (mora) — TEST CLAVE post-fix #33

> Distribución de accounts_receivable por bucket de riesgo. ¿Cuánto está vencido a más de 90 días?

**Validar (snapshot más reciente):**
- Filtra al `MAX(snapshot_date)` (NO agrega los 4,401 registros históricos)
- Bucket 90+_days: **$813.27, 12 clientes** (NO $22,442.85 / 371 filas — eso sería bug #33 reaparecido)
- Bucket current: $761.74, 22 clientes
- Bucket 61-90_days: $187.88, 5 clientes
- Bucket 1-30_days: $180.82, 5 clientes
- Bucket 31-60_days: $20.06, 1 cliente
- Total expuesto: 45 clientes, $1,964.77

### 5. Cruce entre tablas (multi-step) — TEST CLAVE post-fix #30

> y de las facturas vencidas que mencionaste, ¿qué clientes son los que más deben? cruza con accounts_receivable

(asumiendo que viene después del Test 2 o Test 4 que ya cargó contexto sobre facturas)

**Validar:**
- Ejecuta SQL real (no se salta el step y alucina — eso sería bug #30 reaparecido)
- Top 5 con customer_ids en formato `C000XXX` (NO `CUST-XXXX` — eso es bug #30):
  - C000100 → $167.50
  - C000050 → $111.50
  - C000040 → $109.33
  - C000039 → $84.60
  - C000095 → $80.93
- Hace JOIN entre invoices (status=overdue) y accounts_receivable
- Filtra al snapshot más reciente

### 6. Glosario aplicado al dato

> ¿Qué significa Chargeback en este negocio y en qué tabla se registra?

**Validar:**
- Trae la definición del glosario `TelcoLATAM.Finanzas.Chargeback`
- Sinónimos: Contracargo, Reversal
- Apunta a la tabla `telco_demo.chargebacks` (99 filas) con FQN completo
- Conecta el concepto de negocio con la ubicación física del dato

### 7. P&L mensual (CFO briefing)

> Muestra la tendencia del P&L mensual: ingresos, costos y margen.

**Validar:**
- Lee `pl_monthly` directo (siguiendo el hint del briefing CFO en `agent.py`)
- 7 meses: Nov 2025 → May 2026
- Cifras exactas (sin inventar):

| Mes | Revenue | COGS | Net Income |
|---|---:|---:|---:|
| 2025-11 | $20,809 | $10,289 | **+$4,534** ← único positivo |
| 2025-12 | $25,762 | $12,369 | -$1,735 |
| 2026-01 | $23,471 | $12,048 | -$2,090 |
| 2026-02 | $22,828 | $12,687 | -$7,219 |
| 2026-03 | $25,650 | $13,185 | -$3,323 |
| 2026-04 | $24,021 | $13,165 | -$5,891 |
| 2026-05 (parcial) | $3,036 | $2,137 | -$10,877 |

- Identifica el deterioro a partir de Diciembre, marca anomalía 🔴 en Mayo
- Bonus esperado (no autónomo todavía): el insight de break-even *"~30% más revenue o ~25% menos payroll"*. Si no lo cita autónomamente, preguntar explícitamente *"¿cuánto le falta para break-even?"*

## Reproducir números desde tablas crudas

Para comparar contra "lo que el consultor armaría en Excel":

```bash
PGPASSWORD=$SUPABASE_DB_PASSWORD psql -h <vps-host> -p 5433 -U postgres \
  -d postgres -f scripts/compute_pl_from_raw.sql
```

Comparativa lado-a-lado en `docs/temp/PL_validation_consultor_vs_agent.md` (interno, no commiteado largo plazo).

## Anti-patrones — si pasa alguno, abrir issue

- ❌ Saluda en cada turno con "¡Hola! Soy DataGov Analyst…" (regresión de #27)
- ❌ Inventa customer_ids tipo `CUST-XXXX` o montos no reales (regresión de #30)
- ❌ Reporta AR como $22K+ en bucket 90+ (regresión de #33 — no filtró snapshot)
- ❌ Aplana la jerarquía del glosario en lista plana (regresión de #28)
- ❌ Usa `telco_demo_vanilla` cuando la pregunta era sobre `telco_demo`
- ❌ Sugiere clustering, predicción, ML — fuera de alcance
- ❌ Hace SQL sin antes consultar OpenMetadata para entender contexto
- ❌ Devuelve respuestas largas sin números concretos cuando los datos están

## Reportar resultados

Si algún test falla:
1. Captura del chat completo
2. Copia del SQL ejecutado (visible en logs streamlit)
3. Validación manual:
   ```bash
   PGPASSWORD=$SUPABASE_DB_PASSWORD psql -h <vps-host> -p 5433 -U postgres \
     -d postgres -c "<query equivalente>"
   ```
4. Abrir GitHub Issue con label apropiado, referenciando el test que falló y el bug previo si aplica (#27/#28/#30/#33)

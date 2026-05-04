# Quick Finance Test

Plan corto para validar que el agente responde bien sobre la capa financiera del demo telco (issue [galacticaia-gov#98](https://github.com/GalacticaIA/galacticaia-gov/issues/98)).

## Pre-requisitos

- Streamlit corriendo en http://<vps-host>:4005
- Sidebar muestra: `OpenMetadata: http://<vps-host>:8592` · `openmetadata (6 tools)` ✅ · `sql (5 tools)` ✅
- Schema `telco_demo` con 17 tablas (6 originales + 6 financieras + 5 de costos/P&L)
- Glosario `TelcoLATAM` con jerarquía Marketing / Finanzas / Operacion

## Datos esperados (verificación previa, lado Postgres)

| Tabla | Filas |
|---|---|
| invoices | 281 |
| payments | 229 |
| revenue_daily | 720 |
| arpu_monthly | 24 |
| accounts_receivable | 4,401 |
| chargebacks | 99 |
| marketing_spend | 95 |
| pl_monthly | 7 |

Si los conteos cambiaron por re-ingesta, ajustar expectativas.

## Tests

Ejecutar uno por uno y validar el resultado contra los criterios de la columna derecha.

### 1. Catálogo: glosario financiero

> ¿Qué glosarios y términos financieros hay disponibles en el catálogo?

**Validar:**
- Menciona el glosario `TelcoLATAM`
- Lista al menos: ARPU, MRR, Invoice, Payment, AccountsReceivable, Chargeback, Revenue, Recharge
- Reconoce la jerarquía padre/hijo (Marketing / Finanzas / Operacion)

### 2. Perfil de tabla (catálogo + SQL)

> Perfila la tabla invoices de telco_demo: estructura, calidad de datos y distribución por status.

**Validar:**
- Trae descripción y FQN desde OpenMetadata (`Supabase-TelcoDemo.postgres.telco_demo.invoices`)
- 281 filas, 12 columnas, 0% nulos
- Distribución de `status`: paid (~73%), issued (~16%), overdue (~11%)
- Marca `base_amount` y `total_amount` con outliers (max ~99k vs avg ~2k)

### 3. Pregunta de negocio (SQL puro)

> ¿Cuál es el ARPU promedio por segmento de cliente en el último mes disponible?

**Validar:**
- Detecta la tabla `arpu_monthly` (24 filas)
- Hace GROUP BY por segmento y filtra por mes
- Devuelve un valor numérico por segmento, no una explicación genérica

### 4. Cuentas por cobrar (mora)

> Distribución de accounts_receivable por bucket de riesgo. ¿Cuánto está vencido a más de 90 días?

**Validar:**
- Identifica la columna del bucket de riesgo (debería ser `risk_bucket` o similar)
- 4,401 filas en total
- Devuelve cifras por bucket con porcentaje
- No inventa columnas que no existen — si no hay bucket >90, lo dice

### 5. Cruce entre tablas

> ¿Qué clientes tienen mayor saldo en accounts_receivable y cuántas facturas vencidas tienen?

**Validar:**
- Hace JOIN entre `accounts_receivable` y `invoices` (por customer_id)
- Filtra invoices con status = 'overdue'
- Devuelve top 5-10 con saldo y conteo
- No alucina — el customer_id debe existir en customers

### 6. Glosario aplicado

> ¿Qué significa Chargeback en este negocio y en qué tabla se registra?

**Validar:**
- Trae la definición del glosario (`TelcoLATAM.Finanzas.Chargeback`)
- Apunta a la tabla `telco_demo.chargebacks` (99 filas)
- Conecta el concepto de negocio con el dato concreto

### 7. P&L mensual

> Muestra la tendencia del P&L mensual: ingresos, costos y margen.

**Validar:**
- Detecta `pl_monthly` (solo 7 filas, 25 columnas)
- Devuelve serie temporal por mes
- Identifica columnas de ingreso vs costo
- Si los nombres de columna no son claros, usa el catálogo OM para entenderlos

## Rollback rápido (si algo se rompe)

```bash
cd ~/projects/agents/agent-data-analyst
cp .env.vanilla.bak .env
# Reiniciar streamlit:
pkill -f "streamlit run app.py" && sleep 2
nohup ./.venv/bin/python -m streamlit run app.py \
  --server.port 4005 --server.address <vps-host> --server.headless true \
  > /tmp/datagov-streamlit.log 2>&1 &
```

Tag de código bueno-conocido: `om-vanilla-baseline` (local).

## Anti-patrones a vigilar

- ❌ El agente sugiere clustering, predicción, ML — fuera de alcance, debe rechazar
- ❌ Inventa columnas o schemas que no existen
- ❌ Usa `telco_demo_vanilla` cuando la pregunta era sobre `telco_demo`
- ❌ Hace SQL sin antes consultar OpenMetadata para entender contexto
- ❌ Devuelve respuestas largas sin números concretos cuando los datos están disponibles

## Reportar resultados

Si algún test falla:
1. Captura del chat
2. Copia del SQL ejecutado (visible en el debug del agente o en logs streamlit)
3. Verificación manual del dato esperado:
   ```bash
   PGPASSWORD=$SUPABASE_DB_PASSWORD psql -h <vps-host> -p 5433 -U postgres \
     -d postgres -c "<query equivalente>"
   ```

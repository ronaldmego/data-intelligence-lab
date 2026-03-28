# Test 2: perfil_usage_daily

**Status:** OK
**Time:** 29.6s
**Query:** Dame el perfil de la tabla usage_daily en el schema telco_demo
**Expected:** tabla con row count, tipos, nulls%, min/max/avg de voice_minutes y data_mb, detectar anomalías

## Response

## 📊 Perfil: usage_daily

### Contexto (OpenMetadata)
- **Descripción:** Consumo diario agregado: datos, voz y SMS por cliente.
- **Owner:** Sin owner
- **Tags:** (No proporcionado)
- **FQN:** Supabase-GalacticaIA.postgres.telco_demo.usage_daily

### Estructura y Estadísticas

| Columna | Tipo estadístico | Tipo SQL | Nulos % | Valores únicos | Observación |
|---------|-----------------|----------|---------|----------------|-------------|
| id | identificador | bigint | 0% | 891 | min=1 max=891 avg=446.00 |
| customer_id | categórica | character varying | 0% | 67 | Referencia al cliente (PII) |
| usage_date | temporal | date | 0% | 7 | top: 2026-03-27(138), 2026-03-26(138), 2026-03-22(137) |
| data_mb | numérica_continua | numeric | 4% | 837 | min=10.10 max=99999.99 avg=3259.70 |
| voice_minutes | numérica_continua | integer | 0% | 454 | min=-295 max=50000 avg=620.32 |
| sms_count | numérica_continua | integer | 3% | 101 | min=0 max=100 avg=50.39 |
| created_at | temporal | timestamp without time zone | 0% | 14 | top: 2026-03-28 02:34:38.069188(70), 2026-03-28 00:46:12.853754(70), 2026-03-28 02:34:38.112743(69) |

Clasificación de variables:
  • id (bigint): tipo=identificador, únicos=891, nulls=0.0%, gráfico=ninguno — alta cardinalidad — probable ID o clave
  • customer_id (character varying): tipo=categórica, únicos=67, nulls=0.0%, gráfico=tabla — cardinalidad media (67 únicos para 891 filas) — clave foránea o identificador de cliente
  • usage_date (date): tipo=temporal, únicos=7, nulls=0.0%, gráfico=line_chart — baja cardinalidad
  • data_mb (numeric): tipo=numérica_continua, únicos=837, nulls=4.0%, gráfico=histogram — alta cardinalidad
  • voice_minutes (integer): tipo=numérica_continua, únicos=454, nulls=0.0%, gráfico=histogram — alta cardinalidad
  • sms_count (integer): tipo=numérica_continua, únicos=101, nulls=3.0%, gráfico=histogram — cardinalidad media
  • created_at (timestamp without time zone): tipo=temporal, únicos=14, nulls=0.0%, gráfico=line_chart — baja cardinalidad

> **Resumen:** 891 filas · 7 columnas · Contiene datos de consumo diario de clientes, con algunas anomalías en los valores numéricos y un rango de fechas de consumo limitado.

### 💡 Insights automáticos
- **Identificador único:** La columna `id` es un identificador único para cada registro de consumo, con 891 valores únicos para 891 filas.
- **Anomalía en `voice_minutes`:** Se han encontrado valores negativos (mínimo -295) en la columna `voice_minutes`, lo cual es una inconsistencia lógica para minutos de voz consumidos. 🔴
- **Posibles outliers en consumo:** Las columnas `data_mb` (máximo 99999.99) y `voice_minutes` (máximo 50000) muestran valores máximos muy elevados que podrían ser outliers o valores de relleno, lo que merece una investigación. 🔴
- **Concentración de fechas de uso:** Las 5 fechas de consumo más frecuentes (`2026-03-27`, `2026-03-26`, `2026-03-22` y las siguientes dos) representan aproximadamente el 77% de los registros, mostrando una alta concentración del uso en pocos días dentro del período registrado.

### Siguiente paso sugerido
Realizar un análisis de tendencias del consumo (datos, voz, SMS) a lo largo del tiempo, utilizando `usage_date` y `customer_id`. Para asegurar la fiabilidad de este análisis, se recomienda una revisión de calidad de datos previa para investigar los valores anómalos (negativos en `voice_minutes`, posibles outliers en `data_mb` y `voice_minutes`) y la gestión de los valores nulos en `data_mb` y `sms_count`.

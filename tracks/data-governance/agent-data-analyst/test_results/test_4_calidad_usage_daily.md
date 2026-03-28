# Test 4: calidad_usage_daily

**Status:** OK
**Time:** 16.9s
**Query:** Reporte de calidad de la tabla usage_daily en telco_demo
**Expected:** 🔴 voice_minutes (negativos), 🔴 data_mb (valores imposibles)

## Response

## 🔍 Reporte de Calidad: usage_daily

| Columna | Tipo | Nulls % | Únicos | Estado | Observación |
|---------|------|---------|--------|--------|-------------|
| id | bigint | 0% | 891 | 🟢 | Identificador único de registro. |
| customer_id | character varying | 0% | 67 | 🟢 | Identificador de cliente (PII). Cardinalidad esperada para registros diarios de múltiples clientes. |
| usage_date | date | 0% | 7 | 🟢 | Fecha de registro de consumo. Contiene datos para 7 días distintos. |
| data_mb | numeric | 4% | 837 | 🟡 | Consumo de datos en MB. 4% de valores nulos. El valor máximo (99,999.99 MB) es muy alto para un consumo diario, podría indicar outliers o planes de datos ilimitados. |
| voice_minutes | integer | 0% | 454 | 🔴 | Minutos de voz consumidos. Contiene valores negativos (mínimo -295) y un valor máximo extremadamente alto (50,000 minutos), lo que indica errores de registro o outliers severos. |
| sms_count | integer | 3% | 101 | 🟡 | SMS enviados. 3% de valores nulos. |
| created_at | timestamp without time zone | 0% | 14 | 🟢 | Timestamp de creación del registro. |

**Semáforo:**
- 🟢 Verde: nulls < 1%, sin anomalías
- 🟡 Amarillo: nulls 1–10%, o cardinalidad sospechosa
- 🔴 Rojo: nulls > 10%, columna constante, o 100% nula

### 📋 Problemas detectados
- 🔴 `voice_minutes`: La columna presenta valores negativos (mínimo -295) y un valor máximo extremadamente alto (50,000 minutos), lo cual es inconsistente con el concepto de minutos de voz consumidos y sugiere errores graves en la captura o procesamiento de datos.
- 🟡 `data_mb`: El 4% de los registros tienen valores nulos, lo que puede afectar la integridad de los análisis de consumo de datos. Además, el valor máximo de 99,999.99 MB (casi 100 GB) para un consumo diario es inusualmente alto y podría ser un outlier o un error.
- 🟡 `sms_count`: El 3% de los registros tienen valores nulos, lo que puede impactar la precisión de los reportes de uso de SMS.

### 💡 Recomendaciones
- **`voice_minutes`**:
    1.  **Investigar y corregir la fuente:** Identificar por qué se están generando valores negativos y valores máximos tan extremos.
    2.  **Limpieza de datos:** Para los registros existentes, considerar reemplazar los valores negativos con 0 y evaluar si los valores extremadamente altos deben ser capados o marcados como outliers.
    3.  **Validación en origen:** Implementar reglas de validación en el punto de entrada de datos para asegurar que los minutos de voz sean siempre no negativos y dentro de un rango razonable.
- **`data_mb`**:
    1.  **Investigar la causa de los nulos:** Determinar por qué el 4% de los registros carecen de información de consumo de datos.
    2.  **Estrategia de manejo de nulos:** Evaluar si es apropiado imputar estos valores (e.g., con la media, mediana o 0 si no hubo consumo) o si deben ser excluidos de ciertos análisis.
    3.  **Revisar outliers:** Analizar el valor máximo para confirmar si es un consumo real de un usuario o un error de registro, y definir una política para su manejo.
- **`sms_count`**:
    1.  **Investigar la causa de los nulos:** Entender por qué el 3% de los registros tienen valores nulos para el conteo de SMS.
    2.  **Estrategia de manejo de nulos:** Considerar la imputación de estos valores (e.g., con 0 si no hubo SMS, o con la media/mediana) o su exclusión, dependiendo del contexto de uso de la tabla.

### ✅ Resumen de salud
> 4 columnas buenas · 2 columnas con advertencia · 1 columna con problemas

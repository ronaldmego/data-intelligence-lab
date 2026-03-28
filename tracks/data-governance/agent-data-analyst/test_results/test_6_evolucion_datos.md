# Test 6: evolucion_datos

**Status:** OK
**Time:** 17.1s
**Query:** ¿Cómo ha evolucionado el consumo de datos (data_mb) en telco_demo.usage_daily?
**Expected:** line chart de data_mb por fecha

## Response

### Evolución del Consumo de Datos (MB) en telco_demo.usage_daily

El consumo total de datos (data_mb) en la tabla `telco_demo.usage_daily` muestra una evolución variada a lo largo del período analizado (del 21 al 27 de marzo de 2026). La métrica `data_mb` es de tipo numérica continua, lo que nos permite observar su distribución y cambios a lo largo del tiempo.

| Fecha      | Consumo de Datos (MB) | Variación vs anterior |
|------------|-----------------------|-----------------------|
| 2026-03-21 | 332,745.96            | —                     |
| 2026-03-22 | 328,087.87            | -1.4%                 |
| 2026-03-23 | 264,355.20            | -19.4%                |
| 2026-03-24 | 302,405.37            | +14.4%                |
| 2026-03-25 | 428,910.11            | +41.8%                |
| 2026-03-26 | 525,043.13            | +22.4%                |
| 2026-03-27 | 618,532.18            | +17.8%                |

### 💡 Insights automáticos

*   **Tendencia general**: El consumo de datos inició con un nivel moderado, experimentó una caída significativa al principio del período y luego mostró una fuerte tendencia de crecimiento sostenido en los últimos tres días.
*   **Punto más alto y más bajo del período**:
    *   El consumo más alto se registró el **27 de marzo de 2026** con **618,532.18 MB**.
    *   El consumo más bajo se registró el **23 de marzo de 2026** con **264,355.20 MB**.
*   **Variaciones significativas entre períodos consecutivos**:
    *   Se observa una **caída notable del 19.4%** entre el 22 y el 23 de marzo. Asumiendo que el 21 de marzo fue sábado, esta caída se produce entre el domingo y el lunes, lo cual es un patrón interesante que podría indicar menor actividad de datos al inicio de la semana laboral.
    *   Posteriormente, hubo un **fuerte incremento del 41.8%** entre el 24 y el 25 de marzo, marcando el inicio de una fase de crecimiento acelerado.
    *   Los últimos tres días (25, 26 y 27 de marzo) muestran aumentos consecutivos superiores al 17%, indicando un incremento robusto en el consumo de datos hacia el final de la semana.
*   **Estacionalidad o patrones semanales**: Aunque el período de 7 días es corto para establecer una estacionalidad definitiva, se puede inferir un patrón:
    *   El consumo disminuye durante el fin de semana (21-22 de marzo, sábado-domingo) y el inicio de la semana (23 de marzo, lunes).
    *   A partir del martes (24 de marzo), el consumo de datos experimenta un crecimiento constante y significativo, alcanzando su pico el viernes (27 de marzo). Esto podría sugerir un mayor uso de datos durante los días laborales o hacia el final de la semana.

```viz
type: line_chart
col_name: total_data_mb
x_values: 2026-03-21,2026-03-22,2026-03-23,2026-03-24,2026-03-25,2026-03-26,2026-03-27
y_values: 332745.96,328087.87,264355.20,302405.37,428910.11,525043.13,618532.18
x_label: Fecha
title: Evolución del Consumo de Datos (MB)
```

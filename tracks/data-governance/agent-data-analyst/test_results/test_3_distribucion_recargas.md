# Test 3: distribucion_recargas

**Status:** OK
**Time:** 45.9s
**Query:** ¿Cuál es la distribución del monto de recargas en telco_demo.recharges?
**Expected:** histogram de amount, detecta outliers ($99,999)

## Response

Aquí tienes el análisis de la distribución del monto de recargas en `telco_demo.recharges`.

### Distribución del Monto de Recargas en telco_demo.recharges

La columna `amount` es de tipo `NUMERIC` (numérica continua), lo que nos permite analizar la distribución de los valores. Se han agrupado los montos en rangos para entender mejor su comportamiento, utilizando los cuartiles (P25, Mediana, P75) y rangos adicionales para identificar valores atípicos.

| Rango de Monto (USD) | Conteo | % del Total |
|----------------------|--------|-------------|
| < 14.03              | 102    | 24.94%      |
| 14.03 - 26.37        | 102    | 24.94%      |
| 26.37 - 38.32        | 102    | 24.94%      |
| 38.32 - 100          | 94     | 22.98%      |
| 100 - 1000           | 0      | 0.00%       |
| >= 1000              | 9      | 2.20%       |
| **Total**            | **409**| **100.00%** |

### 💡 Insights automáticos

*   **Concentración de Recargas Pequeñas:** La gran mayoría de las recargas (97.8% del total, sumando los rangos `< 14.03` hasta `38.32 - 100`) son por montos inferiores a 100 USD. Esto indica que la base de clientes realiza predominantemente recargas de bajo valor.
*   **Distribución Sesgada y Outliers:** La distribución del monto es altamente sesgada. Aunque el 97.8% de las recargas son menores a 100 USD, existen 9 recargas (2.2% del total) que superan los 1000 USD. Estas recargas de alto valor (con un máximo de 99999.00 USD) elevan significativamente la media (2225.47 USD) en comparación con la mediana (26.37 USD), lo que sugiere la presencia de valores atípicos o transacciones de un tipo diferente (ej. recargas corporativas o de alto volumen).
*   **Brecha en los Montos:** Es notable la ausencia de recargas en el rango de 100 a 1000 USD (0.00%). Esto sugiere una clara distinción entre las recargas "normales" de consumo (por debajo de 100 USD) y un grupo muy pequeño de recargas "masivas" (por encima de 1000 USD), sin un punto intermedio significativo.
*   **Top 3 Rangos:** Los tres rangos de montos más bajos (`< 14.03`, `14.03 - 26.37`, `26.37 - 38.32`) tienen una distribución casi idéntica, cada uno representando aproximadamente el 24.94% del total de recargas.

```viz
type: bar_chart
col_name: amount_bin
categories: < 14.03,14.03 - 26.37,26.37 - 38.32,38.32 - 100,100 - 1000,>= 1000
values: 102,102,102,94,0,9
title: Distribución del Monto de Recargas
```

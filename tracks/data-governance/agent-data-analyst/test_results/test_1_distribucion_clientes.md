# Test 1: distribucion_clientes

**Status:** OK
**Time:** 19.4s
**Query:** ¿Cómo se distribuyen los clientes por customer_type y city en telco_demo?
**Expected:** bar chart de customer_type con %, bar chart de top ciudades

## Response

Aquí tienes el análisis de la distribución de clientes por tipo de cliente y ciudad en la tabla `telco_demo.customers`.

### Distribución de clientes por customer_type y city en telco_demo.customers

La distribución de clientes se ha analizado combinando las categorías de `customer_type` (categórica) y `city` (categórica), mostrando la concentración de clientes en cada segmento y ubicación.

| customer_type | city        | Conteo | % del Total |
| :------------ | :---------- | :----- | :---------- |
| postpaid      | David       | 13     | 13.0%       |
| postpaid      | Chitre      | 10     | 10.0%       |
| postpaid      | Santiago    | 9      | 9.0%        |
| postpaid      | Colon       | 8      | 8.0%        |
| prepaid       | Chitre      | 8      | 8.0%        |
| hybrid        | Colon       | 7      | 7.0%        |
| hybrid        | Santiago    | 7      | 7.0%        |
| prepaid       | Panama City | 7      | 7.0%        |
| prepaid       | Santiago    | 7      | 7.0%        |
| hybrid        | David       | 5      | 5.0%        |
| prepaid       | Colon       | 4      | 4.0%        |
| hybrid        | La Chorrera | 3      | 3.0%        |
| postpaid      | Panama City | 3      | 3.0%        |
| hybrid        | Chitre      | 2      | 2.0%        |
| postpaid      | La Chorrera | 2      | 2.0%        |
| prepaid       | David       | 2      | 2.0%        |
| prepaid       | La Chorrera | 2      | 2.0%        |
| hybrid        | Panama City | 1      | 1.0%        |

El total de clientes en la tabla es 100.

### 💡 Insights automáticos

*   **Top 3 combinaciones de clientes y ciudades:**
    1.  **Postpago en David:** Con 13 clientes, representa el 13.0% del total.
    2.  **Postpago en Chitre:** Con 10 clientes, representa el 10.0% del total.
    3.  **Postpago en Santiago:** Con 9 clientes, representa el 9.0% del total.
*   **Concentración por tipo de cliente:** El tipo de cliente `postpaid` muestra la mayor concentración, especialmente en las ciudades de David, Chitre y Santiago.
*   **Concentración geográfica:** Las ciudades de David, Chitre y Santiago son las que tienen mayor número de clientes en general, especialmente en el segmento postpago.
*   **Valores con menor presencia:** La combinación `hybrid` en `Panama City` es la de menor presencia, con solo 1 cliente (1.0% del total). `La Chorrera` también muestra una baja concentración de clientes en general.
*   **Regla de Pareto (80/20):** Las 5 principales combinaciones (`postpaid - David`, `postpaid - Chitre`, `postpaid - Santiago`, `postpaid - Colon`, `prepaid - Chitre`) suman 48 clientes, lo que representa el 48% del total. Esto indica que casi la mitad de los clientes se concentran en un número relativamente pequeño de segmentos y ubicaciones.

```viz
type: bar_chart
col_name: customer_type_city
categories: postpaid - David,postpaid - Chitre,postpaid - Santiago,postpaid - Colon,prepaid - Chitre,hybrid - Colon,hybrid - Santiago,prepaid - Panama City,prepaid - Santiago,hybrid - David,prepaid - Colon,hybrid - La Chorrera,postpaid - Panama City,hybrid - Chitre,postpaid - La Chorrera,prepaid - David,prepaid - La Chorrera,hybrid - Panama City
values: 13,10,9,8,8,7,7,7,7,5,4,3,3,2,2,2,2,1
title: Distribución de Clientes por Tipo y Ciudad
```

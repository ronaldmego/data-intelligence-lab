# Test 5: ranking_canales

**Status:** OK
**Time:** 11.5s
**Query:** ¿Por qué canal se hacen más recargas en telco_demo.recharges?
**Expected:** bar chart de channel con frecuencias y %, detecta ~3% nulls en channel

## Response

La pregunta del usuario es: "¿Por qué canal se hacen más recargas en telco_demo.recharges?"

Hemos analizado la tabla `telco_demo.recharges` y ejecutado una consulta para agrupar las recargas por canal y contar su frecuencia.

### Distribución de `channel` en `telco_demo.recharges`

El canal por el que se realizan más recargas es **web**, con 89 transacciones, representando el 21.76% del total. Le siguen de cerca los canales 'agent' y 'sms'.

| Valor | Conteo | % del Total |
|-------|--------|-------------|
| web   | 89     | 21.76%      |
| agent | 83     | 20.29%      |
| sms   | 79     | 19.32%      |
| app   | 75     | 18.34%      |
| ussd  | 73     | 17.85%      |
| None  | 10     | 2.44%       |
| **Total** | **409** | **100.00%** |

### 💡 Insights automáticos

*   **Top 3 canales:** Los canales con mayor volumen de recargas son 'web' (21.76%), 'agent' (20.29%) y 'sms' (19.32%). Estos tres canales combinados representan el 61.37% de todas las recargas.
*   **Regla de Pareto:** No se observa una concentración extrema donde el 80% de las recargas provenga de un número muy reducido de canales. Los canales están relativamente distribuidos, con los 3 principales sumando poco más del 60%.
*   **Valor dominante:** Ningún canal supera el 50% de las recargas, lo que indica que la base de clientes utiliza una variedad de canales para sus recargas.
*   **Alerta de datos faltantes 🔴:** Se encontraron 10 recargas (2.44% del total) donde el canal no está especificado (`None`). Aunque no es un porcentaje alto (>10%), es importante investigar la causa de estos valores nulos para asegurar la completitud de los datos y entender si hay un canal no registrado o un error en la captura.

```viz
type: bar_chart
col_name: channel
categories: web,agent,sms,app,ussd,None
values: 89,83,79,75,73,10
title: Distribución de Recargas por Canal
```

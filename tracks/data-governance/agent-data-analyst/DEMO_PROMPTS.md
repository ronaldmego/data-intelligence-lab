# Guía de Prompts para Demo — DataGov Analyst

Prompts sugeridos para presentación del agente, en orden progresivo de complejidad.
Cada prompt muestra una capacidad distinta del agente.

---

## 1. Descubrimiento — "¿Qué datos tenemos?"

```
¿Qué tablas hay disponibles en el schema telco_demo?
```

**Qué esperar:**
- Lista de 6 tablas: customers, plans, recharges, usage_daily, campaigns, campaign_responses
- Descripción de cada tabla desde OpenMetadata (gobernanza)
- No genera gráfico (es inventario)

**Duración estimada:** ~10s

---

## 2. Perfil de tabla — Entender antes de opinar

```
Dame el perfil de la tabla usage_daily en telco_demo
```

**Qué esperar:**
- Tabla con 7 columnas: tipo estadístico, SQL, nulls%, valores únicos, min/max/avg
- Clasificación automática de variables (identificador, categórica, numérica_continua, temporal)
- Insights automáticos:
  - 🔴 `voice_minutes` con valores negativos (min=-295)
  - 🔴 `data_mb` con outlier extremo (max=99,999 MB)
  - Nulls en `data_mb` (4%) y `sms_count` (3%)
- Sugiere siguiente paso de análisis

**Duración estimada:** ~30s

---

## 3. Distribución categórica — Gráfico de barras

```
¿Cómo se distribuyen los clientes por customer_type y city en telco_demo?
```

**Qué esperar:**
- Tabla combinada customer_type × city con conteo y % del total
- Insights: concentración en postpaid, ciudades top (Santiago, Chitre, David)
- **Gráfico:** bar_chart horizontal con las 18 combinaciones

**Duración estimada:** ~20s

---

## 4. Ranking con detección de nulls — Calidad en contexto

```
¿Por qué canal se hacen más recargas en telco_demo.recharges?
```

**Qué esperar:**
- Ranking de 5 canales: web (89), agent (83), sms (79), app (75), ussd (73)
- Porcentajes sobre el total
- 🔴 Detecta 10 registros (2.5%) con canal NULL
- **Gráfico:** bar_chart de canales con frecuencias

**Duración estimada:** ~12s

---

## 5. Distribución numérica con outliers — Detección de anomalías

```
¿Cuál es la distribución del monto de recargas en telco_demo.recharges?
```

**Qué esperar:**
- Estadísticas: min=1.17, max=99,999, media=2,225 vs mediana=26.37
- Diagnóstico: distribución sesgada a la derecha (media >> mediana)
- Outliers: 9 recargas >$10,000 (2.2%)
- Concentración: 97.8% de recargas son <$50
- **Gráfico:** bar_chart por rangos de monto

**Duración estimada:** ~45s

---

## 6. Evolución temporal — Serie de tiempo

```
¿Cómo ha evolucionado el consumo de datos (data_mb) en telco_demo.usage_daily?
```

**Qué esperar:**
- Tabla con consumo total por día (7 días)
- Tendencia al alza con caída puntual el lunes
- Variaciones porcentuales entre días
- Métricas: consumo total semanal (~2.8 TB), pico el viernes
- **Gráfico:** line_chart de evolución diaria

**Duración estimada:** ~18s

---

## 7. Reporte de calidad — Semáforo de datos

```
Reporte de calidad de la tabla usage_daily en telco_demo
```

**Qué esperar:**
- Tabla con semáforo por columna: 🟢 🟡 🔴
- 🔴 `voice_minutes`: valores negativos y máximo extremo (50,000)
- 🟡 `data_mb`: 4% nulls + max sospechoso (99,999 MB)
- 🟡 `sms_count`: 3% nulls
- 🟢 Resto de columnas sin problemas
- Recomendaciones accionables por cada problema
- Resumen: "4 buenas · 2 advertencia · 1 problema"

**Duración estimada:** ~28s

---

## Orden sugerido para el video

| Orden | Prompt | Capacidad que muestra | Gráfico |
|-------|--------|----------------------|---------|
| 1 | Descubrimiento (#1) | El agente conoce el catálogo | No |
| 2 | Perfil (#2) | Combina OpenMetadata + SQL | No (tabla) |
| 3 | Distribución (#3) | Análisis categórico con viz | Sí (bar) |
| 4 | Ranking (#4) | Detección de nulls + ranking | Sí (bar) |
| 5 | Outliers (#5) | Detección de anomalías numéricas | Sí (bar) |
| 6 | Temporal (#6) | Serie de tiempo con tendencia | Sí (line) |
| 7 | Calidad (#7) | Reporte ejecutivo de salud de datos | No (semáforo) |

**Narrativa sugerida:** "Primero descubrimos qué datos hay → luego entendemos su estructura → después analizamos distribuciones y tendencias → finalmente evaluamos la calidad."

---

## Tips para el video

- Ejecutar desde la UI Streamlit (`streamlit run app.py --server.port 4005`)
- Los gráficos aparecen inline en el chat via `st.pyplot`
- Si un gráfico no aparece, repetir la pregunta agregando "muéstrame un gráfico"
- El agente siempre responde en español
- Tiempo total estimado para los 7 prompts: ~3 minutos

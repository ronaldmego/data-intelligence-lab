# Roadmap - Khipu Analytics

> Evolución progresiva: paso firme antes del siguiente.

## Fase 1: Conocer y Describir los Datos

### 1.0 Setup ⬜
- [x] Base desde openmetadata-mcp-client (patrón probado)
- [x] CLAUDE.md con nueva visión
- [x] ROADMAP.md con subfases
- [ ] README.md público actualizado
- [ ] Puerto 4005 registrado
- [ ] Estructura de archivos limpia

### 1.1 Descubrimiento de datos ⬜
- [ ] OpenMetadata MCP conectado y funcionando
- [ ] Listar schemas, tablas, databases
- [ ] Ver linaje de datos
- [ ] Consultar glosario de negocio
- [ ] El agente responde: "¿Qué datos tenemos?"

### 1.2 MCP SQL ⬜
- [ ] Evaluar: MCP Supabase oficial vs custom PostgreSQL
- [ ] Integrar segundo MCP para queries SQL
- [ ] Queries READ-ONLY (seguridad)
- [ ] El agente puede ejecutar SELECT contra las tablas reales

### 1.3 Perfil básico ⬜
- [ ] Row count por tabla
- [ ] Column count y tipos de datos
- [ ] % nulls por columna
- [ ] Cardinalidad (valores únicos)
- [ ] Output tabular claro

### 1.4 Clasificación de variables ⬜
- [ ] Clasificar automáticamente: numérica continua, discreta, categórica, temporal, ordinal, booleana, texto
- [ ] La clasificación guía qué gráficos y análisis aplicar
- [ ] Seguir árbol de decisión de data-to-viz.com

### 1.5 Estadísticas descriptivas + visualización ⬜
- [ ] Numéricas: min, max, avg, median, std, percentiles
- [ ] Categóricas: frecuencias, moda, distribución
- [ ] Gráficos con matplotlib según tipo de variable:
  - 1 numérica → histogram / density
  - 2 numéricas → scatter / boxplot
  - Categórica → bar chart
  - Numérica + Categórica → violin / boxplot por grupo
  - Temporal → line chart / connected scatter
- [ ] Principios de Wilke: no distorsionar, proporción correcta

### 1.6 Top N e insights rápidos ⬜
- [ ] Top 3 valores más frecuentes por categórica
- [ ] Valor más/menos repetido
- [ ] "El 80% de X está en Y categorías"
- [ ] Distribución de percentiles
- [ ] Insights automáticos, solo estadística descriptiva

### 1.7 Detección de tipo de análisis ⬜
- [ ] Fecha + métrica → "Es análisis de tendencia"
- [ ] Categórica vs numérica → "Es análisis de distribución por grupo"
- [ ] 2 numéricas → "Es análisis de correlación"
- [ ] Seguir árbol data-to-viz.com
- [ ] El agente PROPONE qué tipo de análisis hacer

### 1.8 Data quality report ⬜
- [ ] % nulls por columna con semáforo (verde/amarillo/rojo)
- [ ] Duplicados detectados
- [ ] Outliers obvios (>3σ o 1.5*IQR)
- [ ] Consistencia referencial entre tablas
- [ ] Tipos de datos inconsistentes
- [ ] Recomendaciones actionables

---

## Fase 2: Profiling Avanzado ⏸️

> **NO INICIAR** hasta que toda la Fase 1 esté sólida y validada.

- [ ] Correlaciones entre variables (Pearson, Spearman)
- [ ] Detección de anomalías
- [ ] Clustering exploratorio (K-means visual)
- [ ] Feature importance básica
- [ ] Comparaciones entre segmentos

---

## Fase 3: Análisis Predictivo ⏸️

> **MUY LEJANO.** Lección aprendida: no saltar aquí sin fundamento.

- [ ] Segmentación de clientes
- [ ] Predicción de churn
- [ ] Propensity scoring
- [ ] Revenue analytics
- [ ] Modelos explicables (SHAP, feature importance)

---

## Principio Rector

```
Descriptiva → Inferencial → Predictiva
   Fase 1         Fase 2        Fase 3
  (AHORA)       (DESPUÉS)    (MUY DESPUÉS)
```

Cada fase se valida completamente antes de avanzar a la siguiente.

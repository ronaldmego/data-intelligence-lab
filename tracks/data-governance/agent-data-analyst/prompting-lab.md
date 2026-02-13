# Prompting Lab 🧪

Observaciones de cómo se comporta el agente con diferentes tipos de preguntas.
Objetivo: encontrar el sweet spot de orientación en el prompt.

## Contexto
- El agente tiene 2 MCPs: OpenMetadata (catálogo) + SQL (queries directas)
- OpenMetadata: descripciones, tags, linaje, glosario, owner
- SQL: stats reales, conteos, distribuciones
- Prompt actual: "orientar/sugerir" — no obligar

## Hipótesis
- Preguntas técnicas/numéricas → el agente irá a SQL (correcto)
- Preguntas de negocio/contexto → debería ir a OpenMetadata primero
- Preguntas mixtas → debería combinar ambos
- Cuando haya N fuentes, OpenMetadata será crítico para descubrir DÓNDE buscar

---

## Experimentos

### Exp 1: Pregunta técnica directa ✅
**Prompt:** "Dame el perfil de la tabla customers en telco_demo"
**Tool elegida:** `get_table_profile` → MCP: **sql**
**Resultado:** ✅ Eficiente. Fue directo a SQL, generó perfil con insights.
**Observación:** No consultó OpenMetadata. Para esta pregunta está bien — era puramente técnica.

### Exp 2: Pregunta de descubrimiento/documentación ✅
**Prompt:** "¿Qué información tenemos sobre clientes? ¿Hay datos documentados?"
**Tool elegida:** `search_catalog` → MCP: **openmetadata** ✅
**Resultado:** Fue a OpenMetadata correctamente. Encontró tabla `customers` con su descripción.
**Observación:** 🎯 Eligió bien. Pregunta de "qué hay" = catálogo.

### Exp 3: Pregunta de confiabilidad/documentación ✅
**Prompt:** "¿Qué fuentes tenemos sobre campañas de marketing? ¿Cuál tiene mejor documentación?"
**Tool elegida:** `search_catalog` → MCP: **openmetadata** ✅
**Resultado:** Encontró tabla `campaigns`, evaluó documentación disponible.
**Observación:** 🎯 Perfecto. Pregunta de "cuál es más confiable" = catálogo gobernado.

### Exp 4: Pregunta mixta (catálogo + datos reales) ⚠️
**Prompt:** "Dame un resumen de la tabla customers: qué representa según el catálogo y cómo se ven los datos reales"
**Tool elegida:** `get_table_details` → MCP: **openmetadata** (solo uno)
**Resultado:** Dio contexto del catálogo pero NO consultó SQL para datos reales.
**Observación:** ⚠️ Limitación actual: solo puede usar 1 tool por turno.
  El agente eligió OpenMetadata (correcto para la primera parte) pero no pudo
  complementar con SQL. Para preguntas mixtas necesitará multi-tool.

---

## Conclusiones (2026-02-13)

### Lo que funciona bien
1. **El routing es inteligente** — preguntas de descubrimiento → OpenMetadata, técnicas → SQL
2. **La orientación del prompt funciona** — sin obligar, el agente toma buenas decisiones
3. **Respuestas con interpretación** — no solo datos, sino qué significan

### Limitaciones detectadas
1. **Single-tool por turno** — no puede combinar OpenMetadata + SQL en una respuesta
2. **No hay "paso 0" automático** — no consulta catálogo antes de ir a SQL

### Ideas de mejora (backlog)
- [ ] Multi-tool: permitir cadena de 2+ tools en una misma respuesta
- [ ] "Paso 0" opcional: consultar OpenMetadata antes de SQL para dar contexto
- [ ] Evaluar si Gemini Flash es suficiente para el paso de decisión (ahorrar tokens)
- [ ] Probar con más datos/schemas para ver si el routing escala

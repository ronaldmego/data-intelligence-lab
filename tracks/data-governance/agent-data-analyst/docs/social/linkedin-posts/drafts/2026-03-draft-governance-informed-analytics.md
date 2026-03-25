# LinkedIn Post — Governance-Informed Analytics (Post 3 de la Serie Data Stack)

**Estado:** ⬜ Draft
**Serie:** Governance Data Stack → Post 3 (evolución directa del Post 2)
**Post anterior:** MCP Agent + OpenMetadata (6 Mar 2026) — aún creciendo
**Repo:** github.com/ronaldmego/agent-data-analyst (PRIVADO — "escríbeme si quieres verlo")
**Timing sugerido:** 3-5 días después del Post 2 (entre 9-11 Mar), cuando el Post 2 estabilice métricas

---

## Contexto estratégico

**Arco de la serie:**
- Post 1: OpenMetadata (el catálogo, $0) → 138 reacciones, 12 comentarios, 20 reposts
- Post 2: MCP Agent (consultar el catálogo en lenguaje natural) → creciendo
- **Post 3: El agente que ANALIZA datos porque primero entiende el gobierno** ← ESTE

**Concepto diferenciador:**
La mayoría de herramientas de "AI analytics" saltan directo a "dame insights". 
Este agente hace lo contrario: primero consulta el catálogo gobernado (qué datos hay, 
quién los cuida, qué significan), y CON ESE CONTEXTO propone y ejecuta análisis.

No es "otro chatbot que hace SQL". Es un analista que respeta el gobierno.

**Qué funcionó en posts anteriores (replicar):**
- ✅ Hook con problema real ("nadie abre el catálogo" / "los catálogos son poderosos pero...")
- ✅ Stack técnico en bullets con emojis
- ✅ Ejemplo concreto de pregunta → respuesta
- ✅ Video demo como media principal
- ✅ Cierre con pregunta que invita a comentar
- ✅ Frase punch memorable ("governance sin herramientas = Scrum sin Jira")
- ✅ Tono educativo, no vendedor. Ronald muestra, no vende.

---

## Multimedia sugerido

**Formato principal: Video demo (60-90 segundos)**

Grabar con OBS + editar en DaVinci Resolve (mismo workflow del Post 2).

**Guión del video:**
1. **(0-5s)** Pantalla: DataGov Analyst abierto en Streamlit. Pregunta ya escrita.
2. **(5-25s)** Primera pregunta: "Describe la tabla customers"
   - Se ve cómo el agente PRIMERO consulta OpenMetadata → muestra owner, descripción, columnas, tags
   - DESPUÉS ejecuta SQL → muestra row count, distribución, estadísticas
   - Respuesta combinada: contexto de gobierno + datos reales
3. **(25-45s)** Segunda pregunta: "¿Cómo se distribuyen los clientes por plan?"
   - El agente ya tiene contexto de la tabla (paso anterior)
   - Ejecuta GROUP BY → muestra distribución
   - Propone: "Hay 3 segmentos principales, el 72% está en plan básico"
4. **(45-60s)** Tercera pregunta (power move): "¿Qué tablas no tienen owner asignado?"
   - Consulta OpenMetadata → lista tablas sin governance
   - Esto es puro gobierno: el agente AUDITA el catálogo
5. **(60-70s)** Pantalla final con stack técnico + "escríbeme si quieres saber más"

**Tips de producción (lecciones del Post 2):**
- Velocidad 1.5x en las partes de espera del LLM
- Subtítulos en las preguntas (texto grande, legible en mobile)
- Sin voz — solo texto en pantalla + UI. LinkedIn autoplay es sin sonido.
- Resolución: 1080x1080 o 1080x1350 (mejor en feed mobile que 16:9)

**Alternativa si no hay tiempo para video:**
Screenshot compuesto: 2-3 capturas del chat mostrando el flujo 
(pregunta → consulta gobierno → analiza datos → respuesta con contexto)

---

## Benchmark: Estructura que funciona

### Post 2 de Ronald (6 Mar) — Estructura real publicada:
```
HOOK practitioner     → "Construí un agente de Gobierno de Datos con OpenMetadata"
PROBLEMA (2-3 líneas) → catálogos poderosos pero nadie los abre
SOLUCIÓN (1 línea)    → agente conversacional via MCP
DIFERENCIADOR         → 100% local. 100% open source. Datos no salen de tu infra.
BULLETS con emojis    → 📖 Catálogo · 🔗 Lineage · 📊 Calidad · 📚 Glosario · ✏️ Escritura
STACK (1 línea)       → Openmetadata · Python · FastMCP · Streamlit · Gemini Free Tier
EJEMPLO → / ←         → pregunta literal → respuesta literal
CTA suave             → "estoy a un chat de distancia"
PUNCH LINE            → "governance sin herramientas = Scrum sin Jira"
REFERENCIA serie      → "(Este es el agente que mencioné en mi post anterior)"
HASHTAGS              → #DataGovernance #MCP #AI #OpenMetadata
```

### Patchy (173K) — Estructura dominante:
```
HOOK emotivo          → "Finally! X that actually works!"
(SUBTÍTULO viral)     → "(it's open-source, and runs locally)"
PROBLEMA (2-3 líneas) → por qué esto importa
BULLETS features      → 5-8 items cortos
VIDEO/IMAGEN          → siempre
LINK repo             → siempre
```

### Diferenciador Ronald vs Patchy/Sumanth/Shubham:
- Patchy = curador invisible. Ronald = **practitioner que opina** ("Construí", "Mi solución")
- Patchy nunca da opinión. Ronald sí — y la punch line memorable es su marca.
- Ronald habla en español, nicho Data Governance (premium, menos competido)
- Los 3 referentes tienen 50K-350K followers haciendo repo reviews. Ronald no compite ahí — compite en **"yo lo construí y esto aprendí"**

### Serie actual — métricas:
| # | Post | Fecha | React | Comm | Reposts | Formato |
|---|------|-------|-------|------|---------|---------|
| 1 | OpenMetadata (catálogo $0) | 4 Mar | 138 | 12 | 20 | Screenshot UI |
| 2 | MCP Agent (consulta catálogo) | 6 Mar | creciendo | — | — | Video demo |
| 3 | **Governance-Informed Analytics** | ~10 Mar | — | — | — | **Video demo** |

---

## Tres opciones de copy

---

### Opción A — Evolución natural, replica estructura Post 2 (RECOMENDADA)
**Tono:** Exacto al Post 2. Practitioner, educativo, evolución de serie.

```
Le enseñé a mi agente de Gobierno de Datos a analizar datos. Con una regla: primero entiende, después opina.

El problema: la mayoría de herramientas de "AI analytics" saltan directo a ejecutar queries. No saben quién gobierna esa tabla, si los datos pasaron tests de calidad, ni qué significan las columnas.

Mi solución: un agente que consulta el catálogo gobernado ANTES de analizar.

100% local. 100% open source. Tus datos no salen de tu infraestructura.

Dos capas conectadas via MCP (Model Context Protocol):
📖 Gobierno — owner, descripción, glosario, tests de calidad (OpenMetadata)
📊 Análisis — estadísticas, distribuciones, anomalías (SQL directo)

Stack: OpenMetadata · PostgreSQL · Python · FastMCP · Streamlit · Gemini (costo ~$0 por query)

Ejemplo real (ver video 👇):
→ "Analiza la tabla customers"
← "5,000 registros. Owner: equipo CRM. 3 tests de calidad activos.
    Distribución por plan: 72% básico, 18% premium, 10% enterprise.
    El campo phone tiene 12% nulos — revisar con el owner."

No saltó directo a los números. Primero entendió el contexto. Después analizó con fundamento.

Si te interesa saber más sobre Gobierno, Agentes, estoy a un chat de distancia.

Un agente que analiza sin entender el gobierno de los datos es como un consultor que opina sin leer el brief.

(Evolución del agente que mostré en mi post anterior sobre OpenMetadata)

#DataGovernance #MCP #AI #Analytics #OpenSource
```

**Por qué funciona:**
- Hook calca estructura Post 2: "Le enseñé a mi agente..." (practitioner, primera persona)
- Mismo flujo: problema → solución → diferenciador → bullets → stack → ejemplo → CTA → punch line
- Punch line en la misma posición y tono ("governance sin herramientas = Scrum sin Jira" → "analiza sin entender gobierno = consultor sin brief")
- Cross-reference a post anterior (continuidad de serie)
- Largo similar (~850 chars vs ~900 del Post 2)

---

### Opción B — Hook contrarian, más provocador
**Tono:** Cuestiona el status quo. Más debate potencial. Estructura Ronald adaptada.

```
Las herramientas de "AI Analytics" tienen un problema: no saben qué datos están analizando.

Ejecutan queries. Generan gráficos. Te dan "insights". Pero no saben quién gobierna esa tabla, si pasó tests de calidad, ni qué significa "status = 3" en tu negocio.

Construí un agente que hace lo contrario: primero consulta el catálogo gobernado, después analiza.

100% local. 100% open source. Tus datos no salen de tu infraestructura.

Dos capas conectadas via MCP:
📖 Gobierno — OpenMetadata (owner, glosario, calidad, lineage)
📊 Análisis — PostgreSQL (estadísticas reales, distribuciones)

Stack: OpenMetadata · PostgreSQL · Python · FastMCP · Streamlit · Gemini (costo ~$0 por query)

Ejemplo real (ver video 👇):
→ "Analiza la tabla customers"
← Primero va al catálogo: owner, descripción, tests de calidad.
    Después ejecuta SQL: distribuciones, nulls, anomalías.
    Respuesta completa con contexto de gobierno.

Sin contexto, no hay insight confiable.

Si te interesa saber más sobre Gobierno, Agentes, estoy a un chat de distancia.

Analytics sin governance es como diagnosticar sin historia clínica.

#DataGovernance #AI #MCP #Analytics #OpenSource
```

**Por qué funciona:**
- Hook contrarian (patrón que mejor le funciona a Ronald: "La respuesta menos popular...")
- Más confrontacional → potencial de debate en comentarios
- Riesgo: puede alienar gente que usa herramientas de AI analytics → pero genera conversación

---

### Opción C — Hook storytelling, paso a paso visual
**Tono:** Narrativo, muestra el journey del agente. Formato scannable.

```
Le pedí a mi agente: "Analiza la tabla customers." Esto es lo que hizo:

Paso 1 — Consultó el catálogo gobernado (OpenMetadata)
→ Tabla customers, schema telco_demo. Owner: equipo CRM.
→ 12 columnas documentadas. 3 tests de calidad activos.

Paso 2 — Ejecutó el análisis (SQL directo)
→ 5,000 registros. Distribución por plan: 72% básico, 18% premium, 10% enterprise.
→ Campo phone: 12% nulos.

Paso 3 — Conectó los puntos
→ "Los tests de calidad pasan, pero el 12% de nulos en phone es un gap. Sugiero revisar el proceso de captura con el owner (equipo CRM)."

No saltó directo a los números. Primero entendió el contexto.

100% local. 100% open source. Dos MCPs conectados:
1️⃣ OpenMetadata → gobierno del dato
2️⃣ PostgreSQL → datos reales

Stack: OpenMetadata · PostgreSQL · Python · FastMCP · Streamlit · Gemini (~$0/query)

[Video demo 👇]

Si te interesa saber más sobre Gobierno, Agentes, estoy a un chat de distancia.

Así debería funcionar un analista — humano o agente. Primero el brief, después la opinión.

(Evolución del agente que mostré en mi post anterior)

#DataGovernance #MCP #AI #Analytics #OpenMetadata
```

**Por qué funciona:**
- Formato paso-a-paso es muy scannable en LinkedIn (mobile)
- "Paso 3 — Conectó los puntos" es el momento wow
- Más largo que las otras opciones → riesgo de "ver más" que corta engagement
- Pero si el video acompaña, la gente quiere ver los pasos en acción

---

## Recomendación

**Opción A** → Réplica exacta de lo que funciona. Misma estructura, mismo largo, mismo tono. La apuesta más segura para el Post 3 de una serie que está creciendo. No cambiar la fórmula mientras esté funcionando.

**Opción B** → Si quieres provocar debate y más comentarios. Hook contrarian es tu patrón histórico más fuerte (Graph Memory: 337 reactions).

**Opción C** → Mayor potencial viral si el video es bueno. Pero más largo y el "ver más" de LinkedIn puede cortar antes del punch.

## Notas para publicación

- **Timing:** Esperar a que Post 2 estabilice (mínimo 72h, idealmente 4-5 días)
- **Hashtags:** Mantener consistencia con serie (#DataGovernance #MCP siempre)
- **CTA implícito:** "Escríbeme si quieres saber más" — repo privado genera DMs
- **Cross-reference:** Mencionar "post anterior" para que nuevos seguidores revisen la serie
- **NO mencionar:** GalacticaIA, DataGov Analyst (nombre del producto), ni governance de agentes

---

*Draft creado: 7 Mar 2026*
*Fuente: docs/social/linkedin-posts/drafts/2026-03-draft-governance-informed-analytics.md*
*Serie: Governance Data Stack — Post 3*

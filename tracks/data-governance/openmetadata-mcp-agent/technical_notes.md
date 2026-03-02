# Technical Notes

Notas técnicas sobre decisiones de arquitectura, bugs encontrados y lecciones aprendidas.

---

## Arquitectura del agente: limitaciones del routing manual

**Fecha:** 2026-02-13
**Issue:** [#1](https://github.com/ronaldmego/openmetadata-mcp-agent/issues/1)

### Contexto

El agente tiene una arquitectura de "un solo paso":

```
Usuario → LLM decide tool → Ejecuta tool → LLM formatea respuesta
```

Las tools disponibles están definidas de forma estática en tres lugares:
1. `server.py` - la función Python con `@mcp.tool`
2. `app.py` → `TOOLS_INFO` - texto que el LLM lee para decidir
3. `app.py` → `agent_process()` - cadena de `if/elif` que ejecuta la tool

### Problema encontrado

Cuando el usuario preguntó por "dominios", el agente usó `list_databases` porque:
- No existía un tool `list_domains` en `server.py`
- OpenMetadata tiene `/api/v1/domains` pero nadie lo expuso como tool
- El LLM hizo lo mejor con lo disponible: eligió la herramienta más cercana semánticamente

### Diferencia con Claude Desktop

Claude Desktop + MCP tiene ventajas arquitectónicas:
- **Descubrimiento dinámico**: se conecta al MCP server via protocolo y descubre tools automáticamente
- **Loop de reintento**: si un approach falla, el LLM puede probar otra estrategia
- **Parámetros flexibles**: puede pasar parámetros como `entityType: "domain"` a `search_catalog`

Nuestro agente no tiene ninguna de estas capacidades actualmente.

### Lección

Cuando el agente "no encuentra algo", el diagnóstico debe seguir este orden:
1. ¿Existe la tool para esa consulta? → Revisar `server.py`
2. ¿La tool está registrada en el agente? → Revisar `TOOLS_INFO` y `if/elif` en `app.py`
3. ¿El LLM elige la tool correcta? → Revisar el debug expander en la UI
4. ¿La API de OpenMetadata devuelve datos? → Revisar resultado crudo en el debug expander

### Solución de debug

Se agregó un expander colapsable debajo de cada respuesta que muestra:
- **Tool usada** y parámetros
- **Decisión del LLM** (texto crudo)
- **Resultado crudo** de la API (antes del formateo por el LLM)

Esto permite diagnosticar en qué paso falla sin necesidad de logs en consola.

---

## Endpoints de OpenMetadata no cubiertos

**Fecha:** 2026-02-13

El MCP server actualmente solo cubre un subconjunto de la API de OpenMetadata. Endpoints relevantes que aún no tienen tool:

| Endpoint | Descripción | Prioridad |
|----------|-------------|-----------|
| `/api/v1/dataProducts` | Data products del catálogo | Alta |
| `/api/v1/tags` | Tags y clasificaciones | Alta |
| `/api/v1/policies` | Políticas de governance | Media |
| `/api/v1/teams` | Equipos y ownership | Media |
| `/api/v1/users` | Usuarios registrados | Media |
| `/api/v1/pipelines` | Pipelines de datos | Media |
| `/api/v1/dashboards` | Dashboards registrados | Baja |
| `/api/v1/topics` | Topics de messaging | Baja |
| `/api/v1/mlmodels` | Modelos de ML | Baja |

Cada tool nuevo requiere: función en `server.py` + import en `app.py` + entrada en `TOOLS_INFO` + `elif` en routing.

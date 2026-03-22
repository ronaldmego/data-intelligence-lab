# MODEL-BENCHMARKS.md - Khipu Analytics

Comparativo de modelos probados con el agente multi-tool de Khipu.

## Fecha: 2026-02-17

### Setup
- **MCPs:** OpenMetadata (6 tools) + SQL/PostgreSQL (5 tools)
- **DB:** Supabase PostgreSQL, 10 schemas, 54 tablas
- **Provider:** OpenRouter (excepto Gemini directo)
- **Tests:** 2 prompts estándar

### Prompts de test

| Test | Prompt | Valida |
|------|--------|--------|
| T1 - SQL básico | "¿Cuántas tablas hay en la base de datos y cuáles son?" | list_databases → list_schemas |
| T2 - Multi-tool | "Dame el perfil de la tabla assessment_leads del schema becgi" | get_table_details (OM) → get_table_profile (SQL) |

### Resultados

| Modelo | Provider | T1 | T2 | Tiempo T1 | Tiempo T2 | Input/1M | Output/1M | Calidad |
|--------|----------|----|----|-----------|-----------|----------|-----------|---------|
| Gemini 2.5 Pro | Google directo | ✅ | ✅ | ~10s | ~10s | $1.25 | $10.00 | ⭐⭐⭐⭐⭐ |
| Gemini 2.0 Flash | OpenRouter | ✅ | ✅ | ~15s | ~12s | $0.10 | $0.40 | ⭐⭐⭐⭐ |
| DeepSeek V3.2 | OpenRouter | ✅ | ✅ | ~75s | ~45s | $0.26 | $0.38 | ⭐⭐⭐⭐½ |
| DeepSeek R1 (free) | OpenRouter | ❌ timeout | - | >60s | - | $0 | $0 | N/A |

### Observaciones

- **Gemini 2.5 Pro:** El mejor en todo, pero 25x más caro que Flash. Solo para producción con clientes.
- **Gemini 2.0 Flash:** Mejor balance velocidad/costo. Rápido, tool calling consistente.
- **DeepSeek V3.2:** Respuestas más detalladas y ricas que Gemini Flash. 3-5x más lento. Precio similar. Buen candidato para uso donde la velocidad no es crítica.
- **DeepSeek R1 (free):** Demasiado lento, timeout constante. No viable.

### Bugs encontrados durante testing

1. **DB Host:** `localhost` no alcanza Supabase (bindeada a Tailscale `<vps-host>`)
2. **Param naming:** `execute_query(sql:str)` → LLMs siempre envían `query`. Renombrado a `query`.
3. **Intermitencia tool parsing:** Modelos más pequeños a veces no parsean correctamente `TOOL: / PARAMS:`. No es bug de código, es limitación del modelo.

### Recomendación

| Escenario | Modelo | Razón |
|-----------|--------|-------|
| Development/testing | DeepSeek V3.2 | Barato, buenas respuestas |
| Demo/cliente | Gemini 2.5 Flash | Rápido + confiable |
| Producción enterprise | Gemini 2.5 Pro | Máxima calidad |

### Config actual
```env
LLM_PROVIDER=openrouter
OPENROUTER_MODEL=deepseek/deepseek-v3.2
```

Para cambiar a Gemini directo:
```env
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-2.5-flash
```

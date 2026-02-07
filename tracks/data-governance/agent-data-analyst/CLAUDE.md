# Khipu Enterprise

Sistema de gestion empresarial. No deployado actualmente.

## Registro de Puertos (Obligatorio)

Este proyecto comparte servidor con otros proyectos. **Antes de usar o cambiar cualquier puerto:**

1. Consultar el registro central: `~/maintenance/docs/infrastructure/port-registry.md`
2. Verificar que el puerto no este ocupado: `ss -tlnp | grep :<puerto>`
3. Registrar el puerto elegido en el archivo de registro
4. **Nunca usar puertos prohibidos** (3333, 4444, 14444, etc.) — disparan alertas de seguridad

> Este es un requisito mandatorio del servidor. Ver el documento completo para puertos disponibles, rangos asignados y reglas.

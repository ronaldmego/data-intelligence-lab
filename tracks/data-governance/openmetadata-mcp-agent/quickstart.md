# Quick Start - OpenMetadata Agent

## Requisitos previos

- Python 3.10+
- Acceso a una instancia de OpenMetadata (URL + JWT token)
- API key de Google Gemini

## 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

## 2. Configurar credenciales

```bash
cp .env.example .env
```

Editar `.env` con tus valores:

```env
GOOGLE_API_KEY=tu-api-key-de-gemini
OPENMETADATA_URL=http://tu-servidor:8585
OPENMETADATA_TOKEN=tu-jwt-token
GEMINI_MODEL=gemini-2.5-pro
```

**Donde obtener cada valor:**

| Variable | Cómo obtenerla |
|----------|----------------|
| `GOOGLE_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) |
| `OPENMETADATA_URL` | URL de tu instancia de OpenMetadata |
| `OPENMETADATA_TOKEN` | OpenMetadata > Settings > Bots > copiar JWT |
| `GEMINI_MODEL` | `gemini-2.5-pro` (default) o `gemini-2.5-flash` (más rápido/barato) |

## 3. Verificar conexión (opcional)

```bash
python test_connection.py
```

## 4. Ejecutar

```bash
streamlit run app.py --server.port 4004
```

Abrir en el navegador: **http://localhost:4004**

## Exponer en red local

```bash
streamlit run app.py --server.port 4004 --server.address 0.0.0.0
```

## Solución de problemas

| Problema | Solución |
|----------|----------|
| `ModuleNotFoundError` | Ejecutar `pip install -r requirements.txt` |
| Error de conexión a OpenMetadata | Verificar `OPENMETADATA_URL` y que el servidor esté accesible |
| Error 401 Unauthorized | Verificar/rotar `OPENMETADATA_TOKEN` |
| Error de Gemini API | Verificar `GOOGLE_API_KEY` y que tenga cuota disponible |

# OpenMetadata — Arquitectura de Alto Nivel

OpenMetadata no modela sus propios datos. Su propósito es **catalogar el modelo de datos de tus fuentes externas** (bases de datos, data warehouses, dashboards, pipelines, etc.).

Internamente usa MySQL o PostgreSQL como almacén de metadatos, pero ese esquema es un detalle de implementación, no un producto que se exponga al usuario.

## Diagrama

```
┌─────────────────────────────────────────────────────┐
│                    OpenMetadata                      │
│                                                     │
│  ┌────────────────┐    ┌─────────────────────────┐  │
│  │  Ingestion /    │    │   Metadata Store         │ │
│  │  Connectors     │───▶│   (MySQL / PostgreSQL)   │ │
│  │                 │    │                          │ │
│  │                 │    │  ┌────────────────────┐  │ │
│  │                 │    │  │ table_entity       │  │ │
│  │                 │    │  │ dashboard_entity   │  │ │
│  │                 │    │  │ pipeline_entity    │  │ │
│  │                 │    │  │ entity_relationship│  │ │
│  │                 │    │  │ change_event       │  │ │
│  │                 │    │  └────────────────────┘  │ │
│  └───────┬─────────┘    └────────────┬────────────┘  │
│          │                           │               │
│          │                           ▼               │
│          │              ┌─────────────────────────┐  │
│          │              │  Elasticsearch           │  │
│          │              │  (busqueda full-text)    │  │
│          │              └─────────────────────────┘  │
└──────────┼───────────────────────────────────────────┘
           │
           │
     ┌─────┼──────────────────────────────┐
     │     │                              │
     ▼     ▼              ▼               ▼
 ┌──────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
 │MySQL │ │Snowflake │ │Redshift  │ │ Kafka    │
 └──────┘ └──────────┘ └──────────┘ └──────────┘
```

## Flujo

1. **Ingestion/Connectors** se conectan a tus fuentes externas y extraen su metadata (esquemas, tablas, columnas, tipos, lineage).
2. **Metadata Store** almacena esa metadata como documentos JSON en tablas internas (una por tipo de entidad).
3. **Elasticsearch** sincroniza desde el store para ofrecer busqueda full-text.
4. **Tus fuentes** (fila inferior) son los sistemas cuyo modelo de datos realmente te interesa — OpenMetadata los cataloga, no se cataloga a si mismo.

## Referencia

- Repo oficial: https://github.com/open-metadata/OpenMetadata
- JSON Schemas de entidades: https://github.com/open-metadata/OpenMetadata/tree/main/openmetadata-spec/src/main/resources/json/schema/entity

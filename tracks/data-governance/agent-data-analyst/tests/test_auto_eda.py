"""
Test de Auto-EDA de Khipu
"""
import asyncio
import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.connectors.openmetadata import OpenMetadataClient, OpenMetadataConfig
from packages.core.auto_eda import AutoEDA, TableProfile

# Config
OM_HOST = "http://localhost:8585"
OM_TOKEN = os.getenv("OM_TOKEN", "")


async def get_table_details(table_name: str) -> dict:
    """Obtiene detalles de una tabla desde OpenMetadata"""
    config = OpenMetadataConfig(host=OM_HOST, jwt_token=OM_TOKEN)
    async with OpenMetadataClient(config) as client:
        tables = await client.get_tables(limit=50)
        for t in tables:
            if table_name in t.fullyQualifiedName:
                details = await client.get_table(t.fullyQualifiedName)
                return {
                    "name": details.name,
                    "fullyQualifiedName": details.fullyQualifiedName,
                    "description": details.description,
                    "columns": details.columns,
                    "database": {"name": "postgres"}
                }
    return None


async def test_auto_eda():
    """Test del sistema Auto-EDA"""
    print("🧪 Test de Auto-EDA de Khipu\n")
    
    eda = AutoEDA()
    
    # 1. Obtener datos de la tabla customers
    print("📊 Cargando tabla 'customers' desde OpenMetadata...")
    table_data = await get_table_details("telco_demo.customers")
    
    if not table_data:
        print("❌ No se encontró la tabla")
        return
    
    print(f"   ✅ Tabla: {table_data['name']}")
    print(f"   ✅ Columnas: {len(table_data['columns'])}")
    
    # 2. Crear perfil
    print("\n📋 Creando perfil de tabla...")
    # Simulamos row_count ya que no corrimos profiler
    table_data['profile'] = {'rowCount': 1000}
    profile = eda.build_profile_from_openmetadata(table_data)
    
    print(f"   Tamaño: {profile.size_category}")
    print(f"   Tiempo estimado: {profile.estimated_analysis_time}")
    
    # 3. Crear propuesta de análisis
    print("\n🎯 Generando propuesta de análisis...")
    proposal = eda.create_analysis_proposal(profile)
    
    print(f"\n   📊 Resumen:")
    print(f"   - Filas: {proposal['summary']['row_count']}")
    print(f"   - Columnas: {proposal['summary']['column_count']}")
    print(f"   - Categoría: {proposal['summary']['size_category']}")
    
    print(f"\n   📈 Análisis de columnas:")
    for col in proposal['columns_analysis'][:5]:
        print(f"   - {col['name']}: {col['inferred_type']} → {col['suggested_viz']}")
    
    print(f"\n   💡 Análisis sugeridos:")
    for analysis in proposal['suggested_analyses']:
        print(f"   - {analysis['type']}: {analysis['description']}")
    
    # 4. Generar SQL de análisis
    print("\n📝 Generando SQLs de análisis...")
    
    # SQL descriptivo general
    analysis_sql = eda.generate_analysis_sql("customers", table_data['columns'][:3])
    print(f"\n   SQL Descriptivo (primeras 3 columnas):")
    print(f"   {analysis_sql[:200]}...")
    
    # SQL de frecuencias para 'status'
    freq_sql = eda.generate_frequency_sql("customers", "status")
    print(f"\n   SQL Frecuencias (status):")
    print(f"   {freq_sql.strip()}")
    
    # 5. Generar spec de dashboard
    print("\n🖼️  Generando especificación de dashboard...")
    dashboard = eda.generate_dashboard_spec("customers", table_data['columns'][:3])
    
    print(f"   Dashboard: {dashboard['title']}")
    print(f"   Paneles: {len(dashboard['panels'])}")
    for panel in dashboard['panels']:
        print(f"   - {panel['title']} ({panel['type']})")
    
    print("\n✅ Test Auto-EDA completado!")
    
    return proposal, dashboard


if __name__ == "__main__":
    if not OM_TOKEN:
        print("❌ Set OM_TOKEN environment variable")
        sys.exit(1)
    
    asyncio.run(test_auto_eda())

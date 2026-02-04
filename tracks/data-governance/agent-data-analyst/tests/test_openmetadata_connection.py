"""
Test de conexión Khipu → OpenMetadata
Verifica que podemos leer schemas, tablas y metadata del catálogo.
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.connectors.openmetadata import OpenMetadataClient, OpenMetadataConfig

# Configuración
OM_HOST = "http://localhost:8585"
OM_TOKEN = os.getenv("OM_TOKEN", "")  # Set via environment

async def test_connection():
    """Test básico de conexión"""
    config = OpenMetadataConfig(host=OM_HOST, jwt_token=OM_TOKEN)
    
    async with OpenMetadataClient(config) as client:
        # 1. Health check
        healthy = await client.health_check()
        print(f"✅ OpenMetadata healthy: {healthy}")
        
        # 2. Listar tablas
        tables = await client.get_tables(limit=50)
        print(f"✅ Tablas encontradas: {len(tables)}")
        
        # 3. Filtrar por telco_demo
        telco_tables = [t for t in tables if 'telco_demo' in t.fullyQualifiedName]
        print(f"✅ Tablas en telco_demo: {len(telco_tables)}")
        
        for table in telco_tables:
            print(f"   - {table.name}: {table.description or '(sin descripción)'}")
        
        # 4. Obtener detalles de una tabla
        if telco_tables:
            table_fqn = telco_tables[0].fullyQualifiedName
            details = await client.get_table(table_fqn)
            print(f"\n📊 Detalle de {details.name}:")
            print(f"   Columnas: {len(details.columns)}")
            for col in details.columns[:5]:
                print(f"   - {col.get('name')}: {col.get('dataType')}")
        
        return True

if __name__ == "__main__":
    print("🧪 Test de conexión Khipu → OpenMetadata\n")
    
    if not OM_TOKEN:
        print("⚠️  Set OM_TOKEN environment variable")
        print("   export OM_TOKEN='eyJ...'")
        sys.exit(1)
    
    result = asyncio.run(test_connection())
    print(f"\n{'✅ Test passed!' if result else '❌ Test failed'}")

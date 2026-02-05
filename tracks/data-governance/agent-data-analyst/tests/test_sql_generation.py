"""
Test de generación de SQL con Khipu
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.connectors.openmetadata import OpenMetadataClient, OpenMetadataConfig
from packages.core.sql_agent import KhipuSQLAgent

# Config
OM_HOST = "http://localhost:8585"
OM_TOKEN = os.getenv("OM_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Preguntas de prueba
TEST_QUESTIONS = [
    "¿Cuántos clientes churned tenemos?",
    "¿Cuál es el ARPU del último mes?",
    "Top 5 ciudades con más clientes prepago",
    "¿Cuántas recargas se hicieron por canal?",
    "¿Qué campaña tuvo mejor tasa de conversión?",
]


async def get_telco_tables():
    """Obtiene tablas de telco_demo con sus columnas"""
    config = OpenMetadataConfig(host=OM_HOST, jwt_token=OM_TOKEN)
    async with OpenMetadataClient(config) as client:
        tables = await client.get_tables(limit=50)
        telco_tables = [t for t in tables if 'telco_demo' in t.fullyQualifiedName]
        
        result = []
        for table in telco_tables:
            try:
                details = await client.get_table(table.fullyQualifiedName)
                result.append({
                    "name": details.name,
                    "description": details.description,
                    "columns": details.columns
                })
            except Exception as e:
                print(f"⚠️  Error getting {table.name}: {e}")
        
        return result


async def test_sql_generation():
    """Test de generación de SQL"""
    print("🧪 Test de generación SQL\n")
    
    # 1. Obtener schema
    print("📊 Cargando schema de OpenMetadata...")
    tables = await get_telco_tables()
    print(f"   {len(tables)} tablas cargadas\n")
    
    # 2. Crear agente
    agent = KhipuSQLAgent(openai_api_key=OPENAI_API_KEY)
    
    # 3. Probar preguntas
    print("🤖 Generando SQL para preguntas de prueba:\n")
    
    for question in TEST_QUESTIONS:
        print(f"❓ {question}")
        result = await agent.generate_sql(question, tables)
        
        if result.get("error"):
            print(f"   ❌ Error: {result['error']}\n")
        else:
            sql = result.get("sql", "")
            # Mostrar SQL formateado
            print(f"   📝 SQL:")
            for line in sql.split('\n'):
                print(f"      {line}")
            print()
    
    print("✅ Test completado!")


if __name__ == "__main__":
    if not OM_TOKEN:
        print("❌ Set OM_TOKEN environment variable")
        sys.exit(1)
    if not OPENAI_API_KEY:
        print("❌ Set OPENAI_API_KEY environment variable")
        sys.exit(1)
    
    asyncio.run(test_sql_generation())

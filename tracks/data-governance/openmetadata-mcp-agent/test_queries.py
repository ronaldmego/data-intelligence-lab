#!/usr/bin/env python3
"""
Test conversacional del OpenMetadata MCP Server.
Simula queries que un usuario haría en lenguaje natural.
"""

import sys
sys.path.insert(0, '.')
from server import (
    search_catalog, 
    list_tables, 
    get_table_details, 
    list_databases,
    list_glossary_terms
)

def test_query(user_question: str, func, *args, **kwargs):
    """Simular una query conversacional"""
    print(f"\n{'='*60}")
    print(f"🗣️  Usuario: \"{user_question}\"")
    print(f"{'='*60}")
    result = func(*args, **kwargs)
    print(f"\n🤖 Respuesta:\n{result}")
    return result

if __name__ == "__main__":
    print("\n" + "🔬 TEST: OpenMetadata MCP Server - Queries Conversacionales".center(60))
    print("="*60)
    
    # Test 1: Listar todas las tablas
    test_query(
        "¿Qué tablas tenemos en el catálogo?",
        list_tables,
        limit=10
    )
    
    # Test 2: Buscar por término
    test_query(
        "Busca todo lo relacionado con 'assessment'",
        search_catalog,
        query="assessment",
        limit=5
    )
    
    # Test 3: Detalle de una tabla específica
    test_query(
        "¿Qué columnas tiene la tabla assessment_results?",
        get_table_details,
        table_name="assessment_results"
    )
    
    # Test 4: Listar databases
    test_query(
        "¿Qué databases tenemos registradas?",
        list_databases
    )
    
    # Test 5: Buscar leads
    test_query(
        "Muéstrame las tablas de leads",
        search_catalog,
        query="leads",
        limit=5
    )
    
    print("\n" + "="*60)
    print("✅ Tests completados!")
    print("="*60 + "\n")

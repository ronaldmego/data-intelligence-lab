#!/usr/bin/env python3
"""
Test script para verificar que multi-tool reasoning funciona
"""

import asyncio
from agent import create_agent

async def test_simple():
    """Test básico - solo inicialización"""
    print("🔧 Inicializando agent...")
    agent = create_agent()
    
    print("🔍 Descubriendo tools...")
    await agent.discover_tools()
    
    print(f"✅ Tools registradas: {len(agent.tools_registry)}")
    print(f"✅ MCPs conectados: {list(agent.mcp_servers.keys())}")
    
    # Test tools disponibles
    print("\n📋 Tools disponibles:")
    for tool_name, tool_info in list(agent.tools_registry.items())[:5]:  # Solo primeras 5
        print(f"  - {tool_name} (MCP: {tool_info['mcp_name']})")
    
    print("\n✅ Test de inicialización completado exitosamente!")

if __name__ == "__main__":
    asyncio.run(test_simple())
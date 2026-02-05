"""
Test del endpoint POST /api/analyze
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import httpx

API_BASE = "http://localhost:8001"


async def test_analyze_json():
    """Test /api/analyze con output JSON"""
    print("🧪 Test: POST /api/analyze (JSON output)")
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        # Health check
        health = await client.get(f"{API_BASE}/health")
        assert health.status_code == 200, f"Health check failed: {health.text}"
        print("   ✅ API healthy")
        
        # Test analyze endpoint
        response = await client.post(
            f"{API_BASE}/api/analyze",
            json={
                "schema_name": "telco_demo",
                "execute_queries": True,
                "output_format": "json"
            }
        )
        
        assert response.status_code == 200, f"Analyze failed: {response.text}"
        data = response.json()
        
        # Validations
        assert data["schema_name"] == "telco_demo"
        assert data["tables_count"] == 6
        assert "tables_analysis" in data
        assert "summary" in data
        
        print(f"   ✅ Schema: {data['schema_name']}")
        print(f"   ✅ Tables: {data['tables_count']}")
        print(f"   ✅ Total rows: {data['summary']['total_rows']}")
        print(f"   ✅ Execution time: {data['execution_time_ms']}ms")
        
        # Check table stats
        for table in data["tables_analysis"]:
            print(f"   📊 {table['table']}: {table['statistics']['row_count']} rows, {table['statistics']['column_count']} cols")
        
        print("\n✅ JSON test passed!")
        return data


async def test_analyze_html():
    """Test /api/analyze con output HTML"""
    print("\n🧪 Test: POST /api/analyze (HTML output)")
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            f"{API_BASE}/api/analyze",
            json={
                "schema_name": "telco_demo",
                "execute_queries": True,
                "output_format": "html"
            }
        )
        
        assert response.status_code == 200, f"Analyze HTML failed: {response.text}"
        assert "text/html" in response.headers.get("content-type", "")
        
        html = response.text
        assert "<!DOCTYPE html>" in html
        assert "Khipu Auto-EDA" in html
        assert "telco_demo" in html
        assert "chart.js" in html.lower()
        
        # Count charts
        chart_count = html.count("new Chart")
        print(f"   ✅ Charts generated: {chart_count}")
        
        # Count table sections
        section_count = html.count("table-section")
        print(f"   ✅ Table sections: {section_count}")
        
        print("\n✅ HTML test passed!")
        return html


async def test_dashboard_shortcut():
    """Test GET /api/analyze/{schema}/dashboard"""
    print("\n🧪 Test: GET /api/analyze/telco_demo/dashboard")
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.get(f"{API_BASE}/api/analyze/telco_demo/dashboard")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        
        print("   ✅ Dashboard shortcut works!")


async def main():
    print("=" * 60)
    print("🔬 Khipu Auto-EDA Endpoint Tests")
    print("=" * 60)
    
    try:
        await test_analyze_json()
        await test_analyze_html()
        await test_dashboard_shortcut()
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

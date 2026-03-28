#!/usr/bin/env python3
"""
Test cases for Issue #20 — Validación con datos reales (telco_demo)
Runs each test case sequentially and saves results to test_results/
"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

# Setup
os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))

RESULTS_DIR = Path(__file__).parent / "test_results"
RESULTS_DIR.mkdir(exist_ok=True)

TEST_CASES = [
    {
        "id": 1,
        "name": "distribucion_clientes",
        "query": "¿Cómo se distribuyen los clientes por customer_type y city en telco_demo?",
        "expected": "bar chart de customer_type con %, bar chart de top ciudades",
    },
    {
        "id": 2,
        "name": "perfil_usage_daily",
        "query": "Dame el perfil de la tabla usage_daily en el schema telco_demo",
        "expected": "tabla con row count, tipos, nulls%, min/max/avg de voice_minutes y data_mb, detectar anomalías",
    },
    {
        "id": 3,
        "name": "distribucion_recargas",
        "query": "¿Cuál es la distribución del monto de recargas en telco_demo.recharges?",
        "expected": "histogram de amount, detecta outliers ($99,999)",
    },
    {
        "id": 4,
        "name": "calidad_usage_daily",
        "query": "Reporte de calidad de la tabla usage_daily en telco_demo",
        "expected": "🔴 voice_minutes (negativos), 🔴 data_mb (valores imposibles)",
    },
    {
        "id": 5,
        "name": "ranking_canales",
        "query": "¿Por qué canal se hacen más recargas en telco_demo.recharges?",
        "expected": "bar chart de channel con frecuencias y %, detecta ~3% nulls en channel",
    },
    {
        "id": 6,
        "name": "evolucion_datos",
        "query": "¿Cómo ha evolucionado el consumo de datos (data_mb) en telco_demo.usage_daily?",
        "expected": "line chart de data_mb por fecha",
    },
]


async def run_test(agent, tc):
    """Run a single test case and save result."""
    print(f"\n{'='*60}")
    print(f"TEST {tc['id']}: {tc['name']}")
    print(f"Query: {tc['query']}")
    print(f"{'='*60}")

    start = datetime.now()
    try:
        result = await agent.process(tc["query"])
        elapsed = (datetime.now() - start).total_seconds()
        status = "OK"
    except Exception as e:
        result = f"ERROR: {str(e)}"
        elapsed = (datetime.now() - start).total_seconds()
        status = "ERROR"

    # Save to file
    output_file = RESULTS_DIR / f"test_{tc['id']}_{tc['name']}.md"
    with open(output_file, "w") as f:
        f.write(f"# Test {tc['id']}: {tc['name']}\n\n")
        f.write(f"**Status:** {status}\n")
        f.write(f"**Time:** {elapsed:.1f}s\n")
        f.write(f"**Query:** {tc['query']}\n")
        f.write(f"**Expected:** {tc['expected']}\n\n")
        f.write(f"## Response\n\n{result}\n")

    print(f"\n[{status}] {elapsed:.1f}s — saved to {output_file.name}")
    return {"id": tc["id"], "name": tc["name"], "status": status, "time": elapsed}


async def main():
    # Run specific test or all
    test_id = int(sys.argv[1]) if len(sys.argv) > 1 else None

    from agent import create_agent
    agent = create_agent()
    await agent.discover_tools()
    print(f"Agent ready: {len(agent.tools_registry)} tools")

    cases = [tc for tc in TEST_CASES if tc["id"] == test_id] if test_id else TEST_CASES
    results = []
    for tc in cases:
        r = await run_test(agent, tc)
        results.append(r)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in results:
        print(f"  Test {r['id']}: {r['status']} ({r['time']:.1f}s) — {r['name']}")


if __name__ == "__main__":
    asyncio.run(main())

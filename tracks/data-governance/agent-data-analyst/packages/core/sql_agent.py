"""
Khipu SQL Agent
Genera SQL a partir de lenguaje natural usando contexto de OpenMetadata
"""
import os
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# System prompt con contexto de telco
SYSTEM_PROMPT = """Eres un experto en SQL para una empresa de telecomunicaciones (telco) en Venezuela.
Tu trabajo es convertir preguntas en lenguaje natural a consultas SQL.

## Base de datos disponible
Schema: telco_demo (PostgreSQL)

### Tablas y columnas:
{schema_context}

### Glosario de negocio:
- **churn/churned**: Cliente sin actividad en 30+ días. En la DB: status = 'churned'
- **activo/active**: Cliente con actividad reciente. En la DB: status = 'active'
- **inactivo/inactive**: Cliente sin actividad 15-30 días. En la DB: status = 'inactive'
- **prepago**: Sin contrato, recarga saldo. En la DB: segment = 'prepago'
- **postpago**: Facturación mensual. En la DB: segment = 'postpago'
- **ARPU**: Average Revenue Per User = SUM(amount) / COUNT(DISTINCT customer_id)
- **recarga**: Transacción donde cliente prepago agrega saldo (tabla: recharges)
- **retention**: Campaña para evitar churn
- **win-back**: Campaña para recuperar clientes churned
- **upsell**: Campaña para aumentar consumo/migrar a postpago

## Reglas:
1. SIEMPRE usa el schema telco_demo (ej: telco_demo.customers)
2. Genera SOLO el SQL, sin explicaciones
3. Usa nombres de columnas exactos del schema
4. Para fechas recientes, usa CURRENT_DATE
5. Si no puedes responder, di "NO_SQL: [razón]"

## Ejemplos:
- "¿Cuántos clientes churned hay?" → SELECT COUNT(*) FROM telco_demo.customers WHERE status = 'churned';
- "¿Cuál es el ARPU del último mes?" → SELECT ROUND(SUM(amount)::numeric / COUNT(DISTINCT customer_id), 2) as arpu FROM telco_demo.recharges WHERE recharge_date >= CURRENT_DATE - INTERVAL '30 days';
"""

class KhipuSQLAgent:
    """Agente que convierte lenguaje natural a SQL"""
    
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0
    ):
        self.api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY required")
        
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=self.api_key
        )
        self.parser = StrOutputParser()
    
    def _build_schema_context(self, tables: list) -> str:
        """Construye contexto del schema desde OpenMetadata"""
        lines = []
        for table in tables:
            cols = ", ".join([
                f"{c.get('name')} ({c.get('dataType', 'unknown')})"
                for c in table.get('columns', [])[:10]  # Limitar columnas
            ])
            desc = table.get('description', '')
            lines.append(f"- **{table['name']}**: {desc}")
            lines.append(f"  Columnas: {cols}")
        return "\n".join(lines)
    
    async def generate_sql(
        self,
        question: str,
        tables: list,
        execute: bool = False,
        db_connection: Optional[any] = None
    ) -> dict:
        """
        Genera SQL a partir de una pregunta en lenguaje natural
        
        Args:
            question: Pregunta del usuario
            tables: Lista de tablas con metadata de OpenMetadata
            execute: Si True, ejecuta el SQL y devuelve resultados
            db_connection: Conexión a la DB para ejecutar
        
        Returns:
            dict con sql, result (si execute=True), error (si hay)
        """
        schema_context = self._build_schema_context(tables)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "{question}")
        ])
        
        chain = prompt | self.llm | self.parser
        
        try:
            sql = await chain.ainvoke({
                "schema_context": schema_context,
                "question": question
            })
            
            # Limpiar SQL
            sql = sql.strip()
            if sql.startswith("```"):
                sql = sql.split("```")[1]
                if sql.startswith("sql"):
                    sql = sql[3:]
                sql = sql.strip()
            
            result = {"sql": sql, "question": question}
            
            # Ejecutar si se solicita
            if execute and db_connection and not sql.startswith("NO_SQL"):
                try:
                    cursor = db_connection.cursor()
                    cursor.execute(sql)
                    rows = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
                    result["result"] = {
                        "columns": columns,
                        "rows": [list(row) for row in rows],
                        "row_count": len(rows)
                    }
                except Exception as e:
                    result["execution_error"] = str(e)
            
            return result
            
        except Exception as e:
            return {
                "question": question,
                "error": str(e)
            }


# Función helper para uso rápido
async def ask_khipu(question: str, tables: list, api_key: Optional[str] = None) -> dict:
    """Helper para hacer preguntas rápidas"""
    agent = KhipuSQLAgent(openai_api_key=api_key)
    return await agent.generate_sql(question, tables)

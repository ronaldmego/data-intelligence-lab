"""
Khipu SQL Agent
Genera SQL a partir de lenguaje natural usando contexto de OpenMetadata
"""
import os
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# System prompt genérico - se construye dinámicamente con el schema y glosario
SYSTEM_PROMPT_TEMPLATE = """Eres un experto en SQL y análisis de datos.
Tu trabajo es convertir preguntas en lenguaje natural a consultas SQL.

## Base de datos disponible
Schema: {schema_name} (PostgreSQL)

### Tablas y columnas:
{schema_context}

### Glosario de negocio:
{business_glossary}

## Reglas:
1. SIEMPRE usa el schema {schema_name} (ej: {schema_name}.tabla)
2. Genera SOLO el SQL, sin explicaciones
3. Usa nombres de columnas exactos del schema
4. Para fechas recientes, usa CURRENT_DATE
5. Si no puedes responder, di "NO_SQL: [razón]"
"""

# Glosarios predefinidos por industria (se pueden extender)
INDUSTRY_GLOSSARIES = {
    "telco": """- **churn/churned**: Cliente sin actividad en 30+ días
- **activo/active**: Cliente con actividad reciente
- **inactivo/inactive**: Cliente sin actividad 15-30 días
- **prepago**: Sin contrato, recarga saldo
- **postpago**: Facturación mensual
- **ARPU**: Average Revenue Per User = SUM(amount) / COUNT(DISTINCT customer_id)
- **recarga**: Transacción donde cliente prepago agrega saldo
- **retention**: Campaña para evitar churn
- **win-back**: Campaña para recuperar clientes churned""",
    
    "banca": """- **mora**: Cliente con pagos vencidos
- **activo**: Cuenta con movimientos recientes
- **inactivo**: Cuenta sin movimientos en 90+ días
- **saldo_promedio**: AVG(balance) del período
- **transacción**: Movimiento de dinero (débito/crédito)
- **préstamo/loan**: Crédito otorgado al cliente
- **tasa_mora**: COUNT(en_mora) / COUNT(total_clientes)""",
    
    "retail": """- **churn**: Cliente sin compras en 90+ días
- **ticket_promedio**: AVG(total_compra)
- **frecuencia**: Número de visitas/compras por período
- **recencia**: Días desde última compra
- **LTV**: Lifetime Value = suma total de compras del cliente
- **conversión**: Visitantes que compran / Total visitantes""",
    
    "default": """- Interpreta los términos de negocio según el contexto de las tablas
- Usa COUNT, SUM, AVG según corresponda
- Para análisis temporal, agrupa por fecha/período"""
}

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
    
    def _detect_industry(self, schema_name: str, tables: list) -> str:
        """Detecta la industria basándose en el nombre del schema o tablas"""
        schema_lower = schema_name.lower()
        
        # Detectar por nombre de schema
        if 'telco' in schema_lower or 'telecom' in schema_lower:
            return 'telco'
        elif 'bank' in schema_lower or 'banca' in schema_lower or 'finance' in schema_lower:
            return 'banca'
        elif 'retail' in schema_lower or 'ecommerce' in schema_lower or 'tienda' in schema_lower:
            return 'retail'
        
        # Detectar por nombres de tablas
        table_names = [t.get('name', '').lower() for t in tables]
        table_str = ' '.join(table_names)
        
        if 'recharge' in table_str or 'subscriber' in table_str or 'prepago' in table_str:
            return 'telco'
        elif 'account' in table_str or 'loan' in table_str or 'transaction' in table_str:
            return 'banca'
        elif 'product' in table_str or 'order' in table_str or 'cart' in table_str:
            return 'retail'
        
        return 'default'
    
    async def generate_sql(
        self,
        question: str,
        tables: list,
        schema_name: str,
        industry: Optional[str] = None,
        execute: bool = False,
        db_connection: Optional[any] = None
    ) -> dict:
        """
        Genera SQL a partir de una pregunta en lenguaje natural
        
        Args:
            question: Pregunta del usuario
            tables: Lista de tablas con metadata de OpenMetadata
            schema_name: Nombre del schema (requerido)
            industry: Industria para glosario (telco, banca, retail) - auto-detecta si None
            execute: Si True, ejecuta el SQL y devuelve resultados
            db_connection: Conexión a la DB para ejecutar
        
        Returns:
            dict con sql, result (si execute=True), error (si hay)
        """
        schema_context = self._build_schema_context(tables)
        
        # Auto-detectar industria si no se especifica
        if industry is None:
            industry = self._detect_industry(schema_name, tables)
        
        # Obtener glosario de la industria
        business_glossary = INDUSTRY_GLOSSARIES.get(industry, INDUSTRY_GLOSSARIES['default'])
        
        # Construir prompt dinámico
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            schema_name=schema_name,
            schema_context=schema_context,
            business_glossary=business_glossary
        )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{question}")
        ])
        
        chain = prompt | self.llm | self.parser
        
        try:
            sql = await chain.ainvoke({
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
async def ask_khipu(
    question: str, 
    tables: list, 
    schema_name: str,
    industry: Optional[str] = None,
    api_key: Optional[str] = None
) -> dict:
    """Helper para hacer preguntas rápidas"""
    agent = KhipuSQLAgent(openai_api_key=api_key)
    return await agent.generate_sql(question, tables, schema_name, industry)

import duckdb
import os
from datetime import datetime
from dotenv import load_dotenv
from langchain.agents import Tool, AgentExecutor, create_react_agent
from langchain_groq import ChatGroq
from langchain import hub

load_dotenv(r'C:\Users\user\Desktop\Datasentinel\.env')

DB_PATH = r"C:\Users\user\Desktop\Datasentinel\datasentinel.db"


def run_sql_query(query: str) -> str:
    """
    Runs a read-only SQL query against the DataSentinel database
    and returns the result as text. Use this to inspect any table:
    raw_transactions, transformed_transactions, aggregated_metrics,
    or pipeline_run_logs.
    """
    forbidden = ["DELETE", "DROP", "UPDATE", "INSERT", "ALTER", "TRUNCATE"]
    if any(word in query.upper() for word in forbidden):
        return "ERROR: Only SELECT queries are allowed for safety."

    try:
        con = duckdb.connect(DB_PATH)
        result = con.execute(query).df()
        con.close()
        return result.to_string(max_rows=20)
    except Exception as e:
        return f"Query failed: {str(e)}"


def check_upstream_table(table_name: str) -> str:
    """
    Checks basic health stats of an upstream table: row count,
    and null rate of key columns. Valid table names:
    raw_transactions, transformed_transactions.
    """
    valid_tables = ["raw_transactions", "transformed_transactions"]
    if table_name not in valid_tables:
        return f"Invalid table. Choose from: {valid_tables}"

    con = duckdb.connect(DB_PATH)
    row_count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    null_check = con.execute(f"""
        SELECT 
            SUM(CASE WHEN customer_dest IS NULL THEN 1 ELSE 0 END) AS null_dest
        FROM {table_name}
    """).fetchone()[0]
    con.close()

    return f"Table {table_name}: {row_count:,} rows, {null_check:,} null customer_dest values"


def get_pipeline_logs(limit: int = 5) -> str:
    """
    Returns the most recent pipeline run logs, showing rows ingested,
    processed, dropped, and status for each run. Use this to find
    when and how a pipeline run failed.
    """
    con = duckdb.connect(DB_PATH)
    df = con.execute(f"""
        SELECT run_timestamp, pipeline_version, rows_ingested, 
               rows_processed, rows_dropped, status, error_message
        FROM pipeline_run_logs
        ORDER BY run_timestamp DESC
        LIMIT {limit}
    """).df()
    con.close()
    return df.to_string()


def calculate_business_impact(affected_rows: int, avg_transaction_value: float = 178000) -> str:
    """
    Estimates the rupee value impact of a data quality issue,
    given the number of affected rows. Uses the average transaction
    value from the dataset unless a different value is provided.
    """
    estimated_impact = affected_rows * avg_transaction_value
    return f"Estimated business impact: ₹{estimated_impact:,.0f} across {affected_rows:,} affected rows"


def build_agent():
    tools = [
        Tool(
            name="run_sql_query",
            func=run_sql_query,
            description=run_sql_query.__doc__
        ),
        Tool(
            name="check_upstream_table",
            func=check_upstream_table,
            description=check_upstream_table.__doc__
        ),
        Tool(
            name="get_pipeline_logs",
            func=get_pipeline_logs,
            description=get_pipeline_logs.__doc__
        ),
        Tool(
            name="calculate_business_impact",
            func=calculate_business_impact,
            description=calculate_business_impact.__doc__
        ),
    ]

    llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    groq_api_key=os.getenv("GROQ_API_KEY"),
    temperature=0
)
    

    prompt = hub.pull("hwchase17/react")

    agent = create_react_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=8
    )

    return agent_executor


def investigate_alert(alert_description: str):
    """
    Takes a plain-English alert description and runs the agent
    to investigate root cause using the available tools.
    """
    agent_executor = build_agent()

    task = f"""
    You are a data quality investigator. An alert has been triggered:
    
    {alert_description}
    
    Investigate this issue. Check the relevant tables, look at recent
    pipeline logs if relevant, and calculate the business impact if
    you find a row count affected. Conclude with a short, clear summary
    of what happened, why, and what it cost.
    """

    result = agent_executor.invoke({"input": task})
    return result["output"]


if __name__ == "__main__":
    alert_text = """
    Issue type: silent_row_drop
    Severity: critical
    The aggregated_metrics table shows a day with unusually low
    transaction volume compared to the rest of the dataset.
    """
    answer = investigate_alert(alert_text)
    print("\n\nFINAL ANSWER:\n")
    print(answer)
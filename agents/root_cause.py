import duckdb
import os
from dotenv import load_dotenv
from langchain.agents import Tool, AgentExecutor, create_react_agent
from langchain_groq import ChatGroq
from langchain import hub

load_dotenv(r"C:\Users\user\Desktop\Datasentinel\.env")

DB_PATH = r"C:\Users\user\Desktop\Datasentinel\datasentinel.db"


def run_sql_query(query: str) -> str:
    """
    Runs a read-only SQL query against the DataSentinel database.
    Use this to inspect tables:
    raw_transactions,
    transformed_transactions,
    aggregated_metrics,
    pipeline_run_logs.
    """

    forbidden = [
        "DELETE",
        "DROP",
        "UPDATE",
        "INSERT",
        "ALTER",
        "TRUNCATE"
    ]

    if any(word in query.upper() for word in forbidden):
        return "ERROR: Only SELECT queries are allowed."

    try:
        con = duckdb.connect(DB_PATH)

        result = con.execute(query).df()

        con.close()

        return result.to_string(max_rows=20)

    except Exception as e:
        return f"Query failed: {str(e)}"


def check_upstream_table(input_str: str) -> str:
    """
    Checks basic health stats of an upstream table.

    Valid tables:
    - raw_transactions
    - transformed_transactions
    """

    try:
        table_name = str(input_str).strip().lower()

        valid_tables = [
            "raw_transactions",
            "transformed_transactions"
        ]

        if table_name not in valid_tables:
            return f"Invalid table. Choose from: {valid_tables}"

        con = duckdb.connect(DB_PATH)

        row_count = con.execute(
            f"SELECT COUNT(*) FROM {table_name}"
        ).fetchone()[0]

        null_check = con.execute(f"""
            SELECT
                SUM(
                    CASE
                        WHEN customer_dest IS NULL THEN 1
                        ELSE 0
                    END
                )
            FROM {table_name}
        """).fetchone()[0]

        con.close()

        return (
            f"Table {table_name}: "
            f"{row_count:,} rows, "
            f"{null_check:,} null customer_dest values"
        )

    except Exception as e:
        return f"Error checking table: {str(e)}"


def get_pipeline_logs(input_str: str = "5") -> str:
    """
    Returns recent pipeline logs.

    Input examples:
    5
    10
    show last 10 runs
    """

    try:
        cleaned = "".join(
            c for c in str(input_str)
            if c.isdigit()
        )

        limit = int(cleaned) if cleaned else 5

        con = duckdb.connect(DB_PATH)

        df = con.execute(f"""
            SELECT
                run_timestamp,
                pipeline_version,
                rows_ingested,
                rows_processed,
                rows_dropped,
                status,
                error_message
            FROM pipeline_run_logs
            ORDER BY run_timestamp DESC
            LIMIT {limit}
        """).df()

        con.close()

        return df.to_string()

    except Exception as e:
        return f"Error reading pipeline logs: {str(e)}"


def calculate_business_impact(input_str: str) -> str:
    """
    Estimates business impact.

    Input should be an affected row count.

    Examples:
    1000
    25000
    178241
    """

    try:
        cleaned = "".join(
            c for c in str(input_str)
            if c.isdigit()
        )

        if not cleaned:
            return (
                "Could not calculate impact: "
                "no numeric value found."
            )

        affected_rows = int(cleaned)

        avg_transaction_value = 178000

        estimated_impact = (
            affected_rows *
            avg_transaction_value
        )

        return (
            f"Estimated business impact: "
            f"Rs {estimated_impact:,.0f} "
            f"across {affected_rows:,} affected rows"
        )

    except Exception as e:
        return f"Could not calculate impact: {str(e)}"


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

    agent = create_react_agent(
        llm,
        tools,
        prompt
    )

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
    Investigates a data quality alert.
    """

    agent_executor = build_agent()

    task = f"""
You are a Data Quality Investigator.

An alert has been triggered:

{alert_description}

Investigate the issue.

Use available tools to:
1. Check relevant tables.
2. Review pipeline logs if needed.
3. Estimate business impact if row counts are available.

Conclude with:
- Root cause
- Evidence
- Business impact
- Recommended action
"""

    result = agent_executor.invoke(
        {"input": task}
    )

    return result["output"]


if __name__ == "__main__":

    alert_text = """
Issue type: silent_row_drop
Severity: critical

The aggregated_metrics table shows a day with unusually
low transaction volume compared to the rest of the dataset.
"""

    answer = investigate_alert(alert_text)

    print("\n\nFINAL ANSWER:\n")
    print(answer)
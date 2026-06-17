import pandas as pd
import numpy as np
import duckdb
import uuid
from datetime import datetime, timezone, timedelta

DB_PATH = "datasentinel.db"

def build_aggregated_metrics():
    con = duckdb.connect(DB_PATH)
    
    con.execute("DELETE FROM aggregated_metrics")
    
    con.execute("""
        INSERT INTO aggregated_metrics
        SELECT
            -- Convert step (hour) to date
            DATE '2024-01-01' + INTERVAL (step / 24) DAY AS metric_date,
            transaction_type,
            COUNT(*)                                    AS total_transactions,
            SUM(amount)                                 AS total_volume,
            AVG(amount)                                 AS avg_transaction_value,
            SUM(is_fraud)                               AS fraud_count,
            SUM(is_fraud) * 1.0 / COUNT(*)              AS fraud_rate,
            SUM(CASE WHEN NOT is_balance_mismatch 
                THEN 1 ELSE 0 END) * 1.0 / COUNT(*)    AS success_rate,
            NOW()                                       AS computed_at
        FROM transformed_transactions
        GROUP BY 1, 2
    """)
    
    count = con.execute(
        "SELECT COUNT(*) FROM aggregated_metrics"
    ).fetchone()[0]
    con.close()
    print(f"✅ Aggregated metrics built: {count} rows")

def build_pipeline_logs():
    con = duckdb.connect(DB_PATH)
    con.execute("DELETE FROM pipeline_run_logs")
    
    base_time = datetime.now(timezone.utc) - timedelta(days=7)
    runs = []
    
    # 5 healthy runs
    for i in range(5):
        rows = 71200 + int(np.random.randint(-500, 500))
        runs.append({
            'run_id':           str(uuid.uuid4()),
            'run_timestamp':    base_time + timedelta(days=i),
            'pipeline_version': 'v1.0.0' if i < 3 else 'v1.0.1',
            'rows_ingested':    rows,
            'rows_processed':   rows,
            'rows_dropped':     int(np.random.randint(0, 50)),
            'status':           'SUCCESS',
            'error_message':    None,
            'duration_seconds': round(45.2 + float(np.random.uniform(-5, 5)), 2)
        })
    
    # The silent failure — this is what your agent finds in Week 3
    runs.append({
        'run_id':           str(uuid.uuid4()),
        'run_timestamp':    base_time + timedelta(days=5, hours=2),
        'pipeline_version': 'v1.0.1',
        'rows_ingested':    71200,
        'rows_processed':   34521,   # only processed half
        'rows_dropped':     36679,   # silently dropped the rest
        'status':           'PARTIAL',
        'error_message':    None,    # no error — that's the whole point
        'duration_seconds': 23.1
    })
    
    logs_df = pd.DataFrame(runs)
    con.execute("INSERT INTO pipeline_run_logs SELECT * FROM logs_df")
    con.close()
    print("✅ Pipeline run logs loaded — including 1 silent PARTIAL run")

if __name__ == "__main__":
    build_aggregated_metrics()
    build_pipeline_logs()
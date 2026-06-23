import duckdb
import pandas as pd
from datetime import datetime

DB_PATH = r"C:\Users\user\Desktop\Datasentinel\datasentinel.db"

def detect_volume_drop():
    """
    Detects Issue 1 — Silent Row Drop.
    Uses IQR (Interquartile Range) instead of z-score, since
    transaction volume data here is noisy and skewed, IQR is
    more robust to that than standard deviation based methods.
    """
    con = duckdb.connect(DB_PATH)

    df = con.execute("""
        SELECT metric_date, SUM(total_transactions) AS daily_volume
        FROM aggregated_metrics
        GROUP BY metric_date
        ORDER BY metric_date
    """).df()
    con.close()

    if len(df) < 3:
        print("Not enough days of data to detect volume drop reliably.")
        return None

    q1 = df['daily_volume'].quantile(0.25)
    q3 = df['daily_volume'].quantile(0.75)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr

    flagged = df[df['daily_volume'] < lower_bound]

    if len(flagged) > 0:
        result = {
            "issue_type": "silent_row_drop",
            "severity": "critical",
            "detected_at": datetime.now().isoformat(),
            "flagged_dates": flagged['metric_date'].astype(str).tolist(),
            "lower_bound_expected": round(lower_bound, 0),
            "actual_volume": flagged['daily_volume'].tolist(),
        }
        print(f"FLAGGED — Volume drop detected on {len(flagged)} day(s)")
        print(f"   Lower bound (Q1 - 1.5*IQR): {lower_bound:.0f}")
        print(f"   Found below threshold: {flagged['daily_volume'].tolist()}")
        return result
    else:
        print("Volume looks normal, no drop detected.")
        return None

def detect_value_anomalies():
    """
    Detects Issue 4 — Value Anomaly.
    Flags individual transactions whose amount is statistically
    extreme compared to the overall distribution, using z-score.
    """
    con = duckdb.connect(DB_PATH)

    df = con.execute("""
        SELECT transaction_id, transaction_type, amount
        FROM transformed_transactions
    """).df()
    con.close()

    mean_amount = df['amount'].mean()
    std_amount = df['amount'].std()

    df['z_score'] = (df['amount'] - mean_amount) / std_amount
    flagged = df[df['z_score'] > 4]

    if len(flagged) > 0:
        result = {
            "issue_type": "value_anomaly",
            "severity": "high",
            "detected_at": datetime.now().isoformat(),
            "affected_count": len(flagged),
            "example_amounts": flagged['amount'].head(5).tolist(),
            "normal_avg_amount": round(mean_amount, 2),
        }
        print(f"FLAGGED — {len(flagged)} transactions with extreme amounts")
        print(f"   Normal average: {mean_amount:.2f}")
        print(f"   Examples found: {flagged['amount'].head(5).tolist()}")
        return result
    else:
        print("No value anomalies detected.")
        return None  
    
def detect_schema_drift(acceptable_null_rate=0.02):
    """
    Detects Issue 2 — Schema Drift.
    Compares the current null rate in customer_dest against an
    acceptable baseline. Healthy data should have close to 0% nulls.
    """
    con = duckdb.connect(DB_PATH)

    result_df = con.execute("""
        SELECT 
            COUNT(*) AS total_rows,
            SUM(CASE WHEN customer_dest IS NULL THEN 1 ELSE 0 END) AS null_rows
        FROM transformed_transactions
    """).df()
    con.close()

    total = result_df['total_rows'][0]
    nulls = result_df['null_rows'][0]
    null_rate = nulls / total

    if null_rate > acceptable_null_rate:
        result = {
            "issue_type": "schema_drift",
            "severity": "critical",
            "detected_at": datetime.now().isoformat(),
            "affected_rows": int(nulls),
            "null_rate_pct": round(null_rate * 100, 2),
            "acceptable_rate_pct": round(acceptable_null_rate * 100, 2),
        }
        print(f"FLAGGED — Schema drift in customer_dest")
        print(f"   Null rate: {null_rate*100:.2f}% (acceptable: {acceptable_null_rate*100}%)")
        print(f"   Affected rows: {nulls:,}")
        return result
    else:
        print("No schema drift detected.")
        return None
    
def detect_pipeline_failures(max_acceptable_drop_rate=0.02):
    """
    Detects pipeline runs where too many rows were dropped,
    by reading the pipeline_run_logs audit table directly.
    """
    con = duckdb.connect(DB_PATH)

    df = con.execute("""
        SELECT 
            run_id, run_timestamp, pipeline_version,
            rows_ingested, rows_processed, rows_dropped, status
        FROM pipeline_run_logs
    """).df()
    con.close()

    df['drop_rate'] = df['rows_dropped'] / df['rows_ingested']
    flagged = df[df['drop_rate'] > max_acceptable_drop_rate]

    if len(flagged) > 0:
        result = {
            "issue_type": "pipeline_failure",
            "severity": "critical",
            "detected_at": datetime.now().isoformat(),
            "affected_runs": flagged['run_id'].tolist(),
            "worst_drop_rate_pct": round(flagged['drop_rate'].max() * 100, 1),
        }
        print(f"FLAGGED — {len(flagged)} pipeline run(s) with excessive drops")
        for _, row in flagged.iterrows():
            print(f"   Run {row['run_id'][:8]}... dropped {row['drop_rate']*100:.1f}% of rows, status={row['status']}")
        return result
    else:
        print("All pipeline runs look healthy.")
        return None
    
def detect_duplicates(max_acceptable_rate=0.003):
    """
    Detects Issue 3 — Duplicate transactions, using a window function
    to find near-identical transactions occurring close together.
    """
    con = duckdb.connect(DB_PATH)

    result_df = con.execute("""
        WITH potential_dupes AS (
            SELECT
                transaction_id,
                COUNT(*) OVER (
                    PARTITION BY customer_origin, customer_dest, amount
                    ORDER BY step
                    ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
                ) AS nearby_identical_count
            FROM transformed_transactions
        )
        SELECT
            COUNT(*) AS total_transactions,
            SUM(CASE WHEN nearby_identical_count > 1 THEN 1 ELSE 0 END) AS potential_duplicates
        FROM potential_dupes
    """).df()
    con.close()

    total = result_df['total_transactions'][0]
    dupes = result_df['potential_duplicates'][0]
    dupe_rate = dupes / total

    if dupe_rate > max_acceptable_rate:
        result = {
            "issue_type": "duplicate_records",
            "severity": "medium",
            "detected_at": datetime.now().isoformat(),
            "affected_rows": int(dupes),
            "duplicate_rate_pct": round(dupe_rate * 100, 2),
        }
        print(f"FLAGGED — Duplicate rate too high: {dupe_rate*100:.2f}%")
        print(f"   {dupes:,} potentially duplicated transactions")
        return result
    else:
        print("Duplicate rate within normal range.")
        return None
    
def detect_referential_integrity(max_acceptable_orphans=10):
    """
    Detects Issue 5 — Referential Integrity breaks.
    Flags transactions referencing merchant IDs that no longer exist.
    """
    con = duckdb.connect(DB_PATH)

    result_df = con.execute("""
        SELECT COUNT(*) AS orphaned_count
        FROM transformed_transactions
        WHERE customer_dest LIKE 'MERCHANT_DELETED_%'
    """).df()
    con.close()

    orphaned = result_df['orphaned_count'][0]

    if orphaned > max_acceptable_orphans:
        result = {
            "issue_type": "referential_integrity",
            "severity": "high",
            "detected_at": datetime.now().isoformat(),
            "affected_rows": int(orphaned),
        }
        print(f"FLAGGED — {orphaned} transactions reference deleted merchants")
        return result
    else:
        print("Referential integrity looks fine.")
        return None
    
def run_all_detectors():
    """
    Runs all six detectors in sequence, collects every
    triggered alert into a single list.
    """
    print("=" * 55)
    print("DataSentinel — Running Full Detection Sweep")
    print("=" * 55)

    detectors = [
        detect_volume_drop,
        detect_value_anomalies,
        detect_schema_drift,
        detect_pipeline_failures,
        detect_duplicates,
        detect_referential_integrity,
    ]

    all_alerts = []
    for detector_fn in detectors:
        print(f"\n--- Running {detector_fn.__name__} ---")
        result = detector_fn()
        if result is not None:
            all_alerts.append(result)

    print("\n" + "=" * 55)
    print(f"Detection sweep complete. {len(all_alerts)} alert(s) triggered.")
    print("=" * 55)

    return all_alerts


if __name__ == "__main__":
    alerts = run_all_detectors()
    for alert in alerts:
        print(alert)
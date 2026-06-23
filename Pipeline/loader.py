import pandas as pd
import duckdb
import uuid
from datetime import datetime, timezone

DB_PATH = r"C:\Users\user\Desktop\Datasentinel\datasentinel.db"
CSV_PATH = r"C:\Users\user\Desktop\Datasentinel\data\raw\PS_20174392719_1491204439457_log.csv"


def get_connection():
    return duckdb.connect(DB_PATH)


def create_tables():
    con = get_connection()

    con.execute("""
        CREATE TABLE IF NOT EXISTS raw_transactions (
            transaction_id         VARCHAR,
            step                   INTEGER,
            transaction_type       VARCHAR,
            amount                 DOUBLE,
            customer_origin        VARCHAR,
            balance_origin_before  DOUBLE,
            balance_origin_after   DOUBLE,
            customer_dest          VARCHAR,
            balance_dest_before    DOUBLE,
            balance_dest_after     DOUBLE,
            is_fraud               INTEGER,
            is_flagged_fraud       INTEGER,
            ingested_at            TIMESTAMP,
            pipeline_version       VARCHAR
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS transformed_transactions (
            transaction_id        VARCHAR,
            step                  INTEGER,
            transaction_type      VARCHAR,
            amount                DOUBLE,
            amount_bucket         VARCHAR,
            customer_origin       VARCHAR,
            customer_dest         VARCHAR,
            balance_delta_origin  DOUBLE,
            balance_delta_dest    DOUBLE,
            is_fraud              INTEGER,
            is_flagged_fraud      INTEGER,
            is_balance_mismatch   BOOLEAN,
            transformed_at        TIMESTAMP,
            pipeline_version      VARCHAR
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS aggregated_metrics (
            metric_date            DATE,
            transaction_type       VARCHAR,
            total_transactions     INTEGER,
            total_volume           DOUBLE,
            avg_transaction_value  DOUBLE,
            fraud_count            INTEGER,
            fraud_rate             DOUBLE,
            success_rate           DOUBLE,
            computed_at            TIMESTAMP
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_run_logs (
            run_id              VARCHAR,
            run_timestamp       TIMESTAMP,
            pipeline_version    VARCHAR,
            rows_ingested       INTEGER,
            rows_processed      INTEGER,
            rows_dropped        INTEGER,
            status              VARCHAR,
            error_message       VARCHAR,
            duration_seconds    DOUBLE
        )
    """)

    con.close()
    print("All 4 tables created")


def load_raw_transactions(csv_path: str = CSV_PATH, sample_size: int = 500000):
    print("Reading full CSV file. This covers all 744 steps, so it takes a bit longer.")

    full_df = pd.read_csv(csv_path)

    print(
        f"Full dataset: {len(full_df):,} rows, "
        f"step range {full_df['step'].min()} to {full_df['step'].max()}"
    )

    # Stratified sampling by day
    full_df["day_bucket"] = full_df["step"] // 24

    days_count = full_df["day_bucket"].nunique()
    per_day_target = sample_size // days_count

    df = (
        full_df.groupby("day_bucket", group_keys=False)
        .apply(
            lambda x: x.sample(
                n=min(len(x), per_day_target),
                random_state=1
            )
        )
        .reset_index(drop=True)
    )

    df = df.drop(columns=["day_bucket"])

    print(
        f"Sampled: {len(df):,} rows, "
        f"step range {df['step'].min()} to {df['step'].max()}"
    )

    df = df.rename(columns={
        "type": "transaction_type",
        "nameOrig": "customer_origin",
        "oldbalanceOrg": "balance_origin_before",
        "newbalanceOrig": "balance_origin_after",
        "nameDest": "customer_dest",
        "oldbalanceDest": "balance_dest_before",
        "newbalanceDest": "balance_dest_after",
        "isFraud": "is_fraud",
        "isFlaggedFraud": "is_flagged_fraud"
    })

    df["transaction_id"] = [str(uuid.uuid4()) for _ in range(len(df))]
    df["ingested_at"] = datetime.now(timezone.utc)
    df["pipeline_version"] = "v1.0.0"

    df["step"] = df["step"].astype(int)
    df["amount"] = df["amount"].astype(float)
    df["is_fraud"] = df["is_fraud"].astype(int)
    df["is_flagged_fraud"] = df["is_flagged_fraud"].astype(int)

    con = get_connection()

    con.register("df_view", df)

    con.execute("DELETE FROM raw_transactions")

    con.execute("""
        INSERT INTO raw_transactions
        SELECT
            transaction_id,
            step,
            transaction_type,
            amount,
            customer_origin,
            balance_origin_before,
            balance_origin_after,
            customer_dest,
            balance_dest_before,
            balance_dest_after,
            is_fraud,
            is_flagged_fraud,
            ingested_at,
            pipeline_version
        FROM df_view
    """)

    count = con.execute(
        "SELECT COUNT(*) FROM raw_transactions"
    ).fetchone()[0]

    con.close()

    print(f"Loaded {count:,} rows into raw_transactions")

    return count


if __name__ == "__main__":
    create_tables()
    load_raw_transactions()
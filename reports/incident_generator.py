import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
import os
from dotenv import load_dotenv
from datetime import datetime
from langchain_groq import ChatGroq

load_dotenv(r'C:\Users\user\Desktop\Datasentinel\.env')

AVG_TRANSACTION_VALUE = 178000

# Cache LLM at module level — initialised once, reused
_llm = None


def get_llm():
    global _llm
    if _llm is None:
        _llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            groq_api_key=os.getenv("GROQ_API_KEY"),
            temperature=0
        )
    return _llm


def calculate_business_impact(alert: dict) -> dict:
    issue_type = alert.get("issue_type")
    impact = {}

    if issue_type == "silent_row_drop":
        affected_rows = alert.get("affected_rows", 0)
        if not affected_rows:
            flagged_dates = alert.get("flagged_dates", [])
            actual_volumes = alert.get("actual_volume", [])
            expected = alert.get("mean_expected_volume", 0)
            affected_rows = sum(
                max(0, expected - v) for v in actual_volumes
            )
        revenue_impact = affected_rows * AVG_TRANSACTION_VALUE
        impact = {
            "affected_rows": int(affected_rows),
            "revenue_unaccounted": f"Rs {revenue_impact:,.0f}",
            "business_description": f"Approximately {int(affected_rows):,} transactions missing from revenue dashboard. Daily volume and fraud metrics are understated."
        }

    elif issue_type == "schema_drift":
        affected_rows = alert.get("affected_rows", 0)
        impact = {
            "affected_rows": int(affected_rows),
            "revenue_unaccounted": f"Rs {affected_rows * AVG_TRANSACTION_VALUE:,.0f}",
            "business_description": f"{int(affected_rows):,} transactions have no merchant attribution. Merchant performance reports are unreliable."
        }

    elif issue_type == "value_anomaly":
        affected_count = alert.get("affected_count", 0)
        example_amounts = alert.get("example_amounts", [])
        overstatement = sum(amt - (amt / 1000) for amt in example_amounts[:5])
        impact = {
            "affected_rows": int(affected_count),
            "metric_distortion": f"Rs {overstatement:,.0f} overstatement in sample",
            "business_description": f"{int(affected_count)} transactions have corrupted amounts. Average transaction value metrics are severely inflated."
        }

    elif issue_type == "duplicate_records":
        affected_rows = alert.get("affected_rows", 0)
        impact = {
            "affected_rows": int(affected_rows),
            "count_inflation": f"{alert.get('duplicate_rate_pct', 0):.2f}%",
            "business_description": f"Transaction count inflated by {int(affected_rows):,} duplicates. Fraud rate appears artificially lower than actual."
        }

    elif issue_type == "pipeline_failure":
        drop_rate = alert.get("worst_drop_rate_pct", 0)
        impact = {
            "affected_runs": alert.get("affected_runs", []),
            "drop_rate": f"{drop_rate:.1f}%",
            "business_description": f"Pipeline silently processed only {100-drop_rate:.1f}% of expected rows. All downstream dashboards show incomplete data."
        }

    elif issue_type == "referential_integrity":
        affected_rows = alert.get("affected_rows", 0)
        impact = {
            "affected_rows": int(affected_rows),
            "revenue_unattributed": f"Rs {affected_rows * AVG_TRANSACTION_VALUE:,.0f}",
            "business_description": f"{int(affected_rows):,} transactions reference deleted merchants. Cannot be attributed in performance reports."
        }

    return impact


def generate_incident_report(alert: dict, root_cause_finding: str = None) -> str:
    from rag.retriever import retrieve_context

    impact = calculate_business_impact(alert)

    # k=2 not 3 — saves one embedding lookup call
    query = f"{alert.get('issue_type')} data quality pipeline"
    policy_context = retrieve_context(query, k=2)

    # Shorter, tighter prompt — fewer tokens = faster + cheaper
    prompt = f"""Write a concise internal data incident report with 4 sections.

ALERT: {alert.get('issue_type')} | Severity: {alert.get('severity')}
IMPACT: {impact}
ROOT CAUSE: {root_cause_finding or "Under investigation."}
POLICY CONTEXT: {policy_context[:800]}

Sections to include:
1. EXECUTIVE SUMMARY (2 sentences, for a non-technical manager)
2. TECHNICAL ROOT CAUSE (what broke and where in the pipeline)
3. BUSINESS IMPACT (specific numbers and affected metrics)
4. RECOMMENDED ACTION (concrete next step based on past incidents)

Be specific and concise. No filler sentences."""

    llm = get_llm()
    response = llm.invoke(prompt)
    return response.content


def generate_report_for_alert(alert: dict) -> str:
    print(f"\nGenerating report: {alert.get('issue_type')}")
    report = generate_incident_report(alert)
    print(report)
    return report


if __name__ == "__main__":
    test_alert = {
        "issue_type": "schema_drift",
        "severity": "critical",
        "detected_at": datetime.now().isoformat(),
        "affected_rows": 178241,
        "null_rate_pct": 42.3,
        "acceptable_rate_pct": 2.0
    }
    generate_report_for_alert(test_alert)
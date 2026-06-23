import sys
sys.path.append(r'C:\Users\user\Desktop\Datasentinel')

from Detection.statistical import run_all_detectors
from reports.incident_generator import generate_report_for_alert

def run_full_pipeline():
    print("\n" + "=" * 60)
    print("DataSentinel — Full Pipeline Run")
    print("=" * 60)

    # Step 1: run all detectors
    print("\nSTEP 1: Running detection sweep...")
    alerts = run_all_detectors()
    print(f"\n{len(alerts)} alert(s) detected.")

    # Step 2: generate incident report for each alert
    print("\nSTEP 2: Generating incident reports...")
    reports = []
    for alert in alerts:
        report = generate_report_for_alert(alert)
        reports.append({
            "alert": alert,
            "report": report
        })

    print(f"\nPipeline complete. {len(reports)} incident report(s) generated.")
    return reports


if __name__ == "__main__":
    run_full_pipeline()
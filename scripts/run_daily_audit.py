from datetime import datetime

from core.reports.daily_audit import generate_audit_report


def main():
    today = datetime.now().date()
    html_path = f"logs/daily_audit_report_{today}.html"
    pdf_path = f"logs/daily_audit_report_{today}.pdf"
    report = generate_audit_report(output_html=html_path, output_pdf=pdf_path, report_date=today)
    print(report)


if __name__ == "__main__":
    main()

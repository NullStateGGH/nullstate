"""NullState 360-Degree Department Reporting System.
Per-minute cost tracking, revenue attribution, and unified P&L for all services.

Cost model: cost = base_cost_per_min * minutes + variable_costs
Profit model: profit = revenue - cost_per_minute (per-minute margin)

Departments:
  - Gateway     (API serving, proxy)
  - Model API   (AI inference)
  - MCP Server  (MCP tools)
  - Mail Server (email relay)
  - Hub         (MCP Hub discovery)
  - GitHub      (integration/webhooks)
  - HOD         (autonomous engine)
  - Crawler     (task processing, lead scoring)
  - Feedback    (website feedback loop)
  - Global      (ecosystem intelligence)
  - Billing     (credits, payments)
"""

import os
import json
import time
import sqlite3
import logging
import subprocess
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path
from dataclasses import dataclass, field, asdict
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [REPORTING] %(message)s")
log = logging.getLogger("nullstate-reporting")

DB_PATH = os.environ.get("NULLSTATE_DB_PATH", "src/core/nullstate.db")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "https://localhost:8080")
MODEL_API_URL = os.environ.get("MODEL_API_URL", "http://localhost:8082")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
GEMINI_API_KEY = os.environ.get("NULLSTATE_GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")

START_TIME = time.time()

# Per-minute cost allocation per department
# Base: $0.645/h compute ($0.01075/min) split across departments
# Each department also has proportional resource allocation
DEPARTMENTS = {
    "gateway": {
        "name": "Gateway API",
        "cpu_share": 0.10, "ram_gb": 4,
        "cost_per_min": 0.0012,
    },
    "model_api": {
        "name": "Model API",
        "cpu_share": 0.25, "ram_gb": 16,
        "cost_per_min": 0.0038,
    },
    "mcp": {
        "name": "MCP Server",
        "cpu_share": 0.05, "ram_gb": 2,
        "cost_per_min": 0.0006,
    },
    "mail": {
        "name": "Mail Server",
        "cpu_share": 0.05, "ram_gb": 2,
        "cost_per_min": 0.0006,
    },
    "hub": {
        "name": "MCP Hub",
        "cpu_share": 0.05, "ram_gb": 1,
        "cost_per_min": 0.0004,
    },
    "github": {
        "name": "GitHub Integration",
        "cpu_share": 0.05, "ram_gb": 1,
        "cost_per_min": 0.0004,
    },
    "hod": {
        "name": "HOD Engine",
        "cpu_share": 0.10, "ram_gb": 8,
        "cost_per_min": 0.0012,
    },
    "crawler": {
        "name": "Crawler & Scoring",
        "cpu_share": 0.10, "ram_gb": 4,
        "cost_per_min": 0.0010,
    },
    "feedback": {
        "name": "Website Feedback",
        "cpu_share": 0.05, "ram_gb": 2,
        "cost_per_min": 0.0004,
    },
    "global": {
        "name": "Global Intelligence",
        "cpu_share": 0.10, "ram_gb": 4,
        "cost_per_min": 0.0008,
    },
    "billing": {
        "name": "Billing & Credits",
        "cpu_share": 0.05, "ram_gb": 2,
        "cost_per_min": 0.0003,
    },
}

TOTAL_COST_PER_MIN = sum(d["cost_per_min"] for d in DEPARTMENTS.values())


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS department_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT,
            department TEXT,
            minutes_running REAL,
            cost_usdc REAL,
            revenue_usdc REAL,
            profit_usdc REAL,
            margin_pct REAL,
            requests INTEGER DEFAULT 0,
            errors INTEGER DEFAULT 0,
            status TEXT,
            metrics TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS unified_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT,
            cycle_seconds REAL,
            total_cost REAL,
            total_revenue REAL,
            total_profit REAL,
            profit_per_min REAL,
            revenue_per_min REAL,
            cost_per_min REAL,
            departments_ok INTEGER,
            departments_degraded INTEGER,
            departments_down INTEGER,
            summary TEXT,
            raw_data TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS cost_minute_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department TEXT,
            minutes INTEGER,
            cost REAL,
            revenue REAL,
            profit REAL,
            margin REAL,
            timestamp TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


def service_active(name: str) -> str:
    """Returns 'active', 'timer', or 'inactive'.
    Timer-based oneshot services are reported as 'timer' (not 'inactive')."""
    try:
        r = subprocess.run(["systemctl", "is-active", f"{name}.service"],
                          capture_output=True, text=True, timeout=5)
        status = r.stdout.strip()
        if status == "active":
            return "active"
        # Check if it has a timer that's active
        r2 = subprocess.run(["systemctl", "is-active", f"{name}.timer"],
                           capture_output=True, text=True, timeout=5)
        if r2.stdout.strip() == "active":
            return "timer"
        return "inactive"
    except Exception:
        return "inactive"


def service_uptime_seconds(name: str) -> float:
    try:
        r = subprocess.run(
            ["systemctl", "show", f"{name}.service", "--property=ActiveEnterTimestamp"],
            capture_output=True, text=True, timeout=5
        )
        line = r.stdout.strip()
        if "=" in line:
            ts_str = line.split("=", 1)[1]
            if ts_str:
                from datetime import datetime as dt
                fmt = "%a %Y-%m-%d %H:%M:%S %Z"
                try:
                    parsed = dt.strptime(ts_str, fmt)
                    return (datetime.now() - parsed.replace(tzinfo=None)).total_seconds()
                except Exception:
                    pass
    except Exception:
        pass
    return 0.0


def collect_gateway_metrics() -> Dict:
    """Collect metrics from gateway API."""
    result = {"requests": 0, "errors": 0, "revenue": 0.0, "status": "unknown"}
    try:
        resp = requests.get(f"{GATEWAY_URL}/health", timeout=5, verify=False)
        if resp.status_code == 200:
            data = resp.json()
            result["status"] = "healthy"
            result["requests"] = data.get("tasks", {}).get("total", 0)
            result["revenue"] = data.get("ledger", {}).get("balance", 0.0) * 0.01
    except Exception as e:
        result["status"] = f"error: {e}"
    try:
        resp2 = requests.get(f"{GATEWAY_URL}/api/v1/credits", timeout=5, verify=False)
        if resp2.status_code == 200:
            pass
    except Exception:
        pass
    return result


def collect_model_api_metrics() -> Dict:
    """Collect model API metrics."""
    result = {"requests": 0, "tokens": 0, "revenue": 0.0, "status": "unknown"}
    try:
        resp = requests.get(f"{MODEL_API_URL}/health", timeout=5)
        if resp.status_code == 200:
            result["status"] = "healthy"
    except Exception:
        pass
    try:
        resp = requests.post(f"{OLLAMA_HOST}/api/tags", timeout=5)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            result["ollama_models"] = len(models)
            result["status"] = "healthy"
    except Exception:
        pass
    return result


def collect_billing_metrics() -> Dict:
    """Collect billing engine metrics."""
    result = {"prepaid_balance": 0.0, "total_deposits": 0.0, "total_spent": 0.0, "status": "unknown"}
    try:
        conn = get_db()
        row = conn.execute("SELECT COALESCE(SUM(balance_usdc),0) FROM credits").fetchone()
        result["prepaid_balance"] = row[0] if row else 0.0
        row = conn.execute("SELECT COALESCE(SUM(lifetime_deposits),0) FROM credits").fetchone()
        result["total_deposits"] = row[0] if row else 0.0
        row = conn.execute("SELECT COALESCE(SUM(total_usdc),0) FROM billing_ledger WHERE status='completed'").fetchone()
        result["total_spent"] = row[0] if row else 0.0
        conn.close()
        result["status"] = "healthy"
        result["revenue"] = result["total_deposits"]
    except Exception as e:
        result["status"] = f"error: {e}"
    return result


def collect_database_metrics() -> Dict:
    """Collect database stats."""
    result = {"tasks": 0, "ledger_entries": 0, "signals": 0, "status": "unknown"}
    try:
        conn = get_db()
        result["tasks"] = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        result["ledger_entries"] = conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
        result["signals"] = conn.execute("SELECT COUNT(*) FROM ecosystem_signals").fetchone()[0]
        result["adaptations"] = conn.execute("SELECT COUNT(*) FROM adaptation_decisions").fetchone()[0]
        result["analytics"] = conn.execute("SELECT COUNT(*) FROM analytics_events").fetchone()[0]
        result["status"] = "healthy"
        conn.close()
    except Exception as e:
        result["status"] = f"error: {e}"
    return result


def compute_department_report(department: str, cfg: Dict, minutes_running: float) -> Dict:
    """Compute full P&L for a single department."""
    cost = cfg["cost_per_min"] * minutes_running
    revenue = 0.0
    requests_count = 0
    errors = 0
    status = "unknown"

    svc_name = {
        "gateway": "nullstate-gateway",
        "model_api": "nullstate-model-api",
        "mcp": "nullstate-mcp",
        "mail": "nullstate-mail",
        "hub": "nullstate-hub",
        "github": "nullstate-github",
        "hod": "nullstate-hod",
        "crawler": "nullstate",
        "feedback": "nullstate-feedback",
        "global": "nullstate-global-feedback",
        "billing": "nullstate-gateway",
    }.get(department, department)

    status = service_active(svc_name)

    if department == "gateway":
        m = collect_gateway_metrics()
        revenue = m.get("revenue", 0.0)
        requests_count = m.get("requests", 0)
        status = m.get("status", status)
    elif department == "model_api":
        m = collect_model_api_metrics()
        requests_count = m.get("requests", 0)
        status = m.get("status", status)
    elif department == "billing":
        m = collect_billing_metrics()
        revenue = m.get("revenue", 0.0)
        status = m.get("status", status)
    elif department == "hod":
        m = collect_database_metrics()
        requests_count = m.get("tasks", 0)
        status = m.get("status", status)

    profit = revenue - cost
    margin = (profit / cost * 100) if cost > 0 else 0.0
    revenue_per_min = revenue / minutes_running if minutes_running > 0 else 0.0
    cost_per_min = cost / minutes_running if minutes_running > 0 else 0.0

    return {
        "department": department,
        "name": cfg["name"],
        "minutes_running": round(minutes_running, 1),
        "cost_usdc": round(cost, 6),
        "revenue_usdc": round(revenue, 6),
        "profit_usdc": round(profit, 6),
        "margin_pct": round(margin, 2),
        "revenue_per_min": round(revenue_per_min, 8),
        "cost_per_min": round(cost_per_min, 8),
        "profit_per_min": round(revenue_per_min - cost_per_min, 8),
        "requests": requests_count,
        "errors": errors,
        "status": status,
    }


def generate_report_id() -> str:
    return f"360_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def run_360_report() -> Dict:
    """Generate a complete 360-degree department report."""
    report_id = generate_report_id()
    start_ts = time.time()
    log.info(f"\n{'='*60}\n360-Degree Department Report {report_id}\n{'='*60}")

    total_minutes = (time.time() - START_TIME) / 60.0
    if total_minutes < 1:
        total_minutes = 60.0

    department_reports = []
    total_cost = 0.0
    total_revenue = 0.0
    departments_ok = 0
    departments_degraded = 0
    departments_down = 0

    for dept_key, cfg in DEPARTMENTS.items():
        try:
            report = compute_department_report(dept_key, cfg, total_minutes)
            department_reports.append(report)
            total_cost += report["cost_usdc"]
            total_revenue += report["revenue_usdc"]
            if report["status"] == "active" or report["status"] == "healthy":
                departments_ok += 1
            elif "error" in report["status"] or report["status"] == "inactive":
                departments_down += 1
            else:
                departments_degraded += 1
            log.info(f"  {report['name']:<25} cost=${report['cost_usdc']:<8.6f} rev=${report['revenue_usdc']:<8.6f} "
                     f"profit=${report['profit_usdc']:<8.6f} margin={report['margin_pct']:<6.2f}% status={report['status']}")
        except Exception as e:
            log.warning(f"  {dept_key}: report error - {e}")
            departments_down += 1

    total_profit = total_revenue - total_cost
    profit_per_min = total_profit / total_minutes if total_minutes > 0 else 0.0
    revenue_per_min = total_revenue / total_minutes if total_minutes > 0 else 0.0
    cost_per_min = total_cost / total_minutes if total_minutes > 0 else 0.0

    summary = (
        f"360 Report {report_id}: {total_minutes:.0f} min runtime | "
        f"${total_cost:.6f} cost | ${total_revenue:.6f} revenue | "
        f"${total_profit:.6f} profit | "
        f"${profit_per_min:.8f}/min | "
        f"Depts: {departments_ok}OK/{departments_degraded}deg/{departments_down}down"
    )

    log.info(f"\n{'='*60}")
    log.info("UNIFIED P&L:")
    log.info(f"  Runtime:     {total_minutes:.0f} minutes")
    log.info(f"  Total Cost:  ${total_cost:.6f} (${cost_per_min:.8f}/min)")
    log.info(f"  Total Rev:   ${total_revenue:.6f} (${revenue_per_min:.8f}/min)")
    log.info(f"  Profit:      ${total_profit:.6f} (${profit_per_min:.8f}/min)")
    log.info(f"  Departments: {departments_ok} OK, {departments_degraded} degraded, {departments_down} down")
    log.info(f"  {summary}")
    log.info(f"{'='*60}")

    cycle_seconds = time.time() - start_ts
    try:
        conn = get_db()

        # Store per-department reports
        for dr in department_reports:
            conn.execute(
                "INSERT INTO department_reports (report_id, department, minutes_running, cost_usdc, revenue_usdc, "
                "profit_usdc, margin_pct, requests, errors, status, metrics) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (report_id, dr["department"], dr["minutes_running"], dr["cost_usdc"], dr["revenue_usdc"],
                 dr["profit_usdc"], dr["margin_pct"], dr["requests"], dr["errors"], dr["status"], json.dumps(dr))
            )

        # Store unified report
        unified = {
            "report_id": report_id,
            "cycle_seconds": round(cycle_seconds, 2),
            "total_cost": round(total_cost, 6),
            "total_revenue": round(total_revenue, 6),
            "total_profit": round(total_profit, 6),
            "profit_per_min": round(profit_per_min, 8),
            "revenue_per_min": round(revenue_per_min, 8),
            "cost_per_min": round(cost_per_min, 8),
            "departments_ok": departments_ok,
            "departments_degraded": departments_degraded,
            "departments_down": departments_down,
            "summary": summary,
            "raw_data": json.dumps(department_reports),
        }
        conn.execute(
            "INSERT INTO unified_reports (report_id, cycle_seconds, total_cost, total_revenue, total_profit, "
            "profit_per_min, revenue_per_min, cost_per_min, departments_ok, departments_degraded, "
            "departments_down, summary, raw_data) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (unified["report_id"], unified["cycle_seconds"], unified["total_cost"], unified["total_revenue"],
             unified["total_profit"], unified["profit_per_min"], unified["revenue_per_min"], unified["cost_per_min"],
             unified["departments_ok"], unified["departments_degraded"], unified["departments_down"],
             unified["summary"], unified["raw_data"])
        )

        # Store per-minute cost log entry
        conn.execute(
            "INSERT INTO cost_minute_log (department, minutes, cost, revenue, profit, margin) VALUES (?,?,?,?,?,?)",
            ("all", int(total_minutes), round(total_cost, 6), round(total_revenue, 6),
             round(total_profit, 6), round(profit_per_min * 100000, 4))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"DB store failed: {e}")

    return {
        "report_id": report_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_minutes": round(total_minutes, 1),
        "departments": department_reports,
        "unified": {
            "total_cost": round(total_cost, 6),
            "total_revenue": round(total_revenue, 6),
            "total_profit": round(total_profit, 6),
            "profit_per_min": round(profit_per_min, 8),
            "revenue_per_min": round(revenue_per_min, 8),
            "cost_per_min": round(cost_per_min, 8),
        },
        "summary": summary,
    }


def review_reports(report: Dict) -> str:
    """Use AI to review and analyze the 360 report, generating insights."""
    dept_lines = []
    for d in report.get("departments", []):
        dept_lines.append(
            f"- {d['name']}: cost=${d['cost_usdc']:.6f} rev=${d['revenue_usdc']:.6f} "
            f"profit=${d['profit_usdc']:.6f} margin={d['margin_pct']:.1f}% status={d['status']}"
        )

    prompt = f"""You are NullState's CFO AI. Review this 360-degree operational report:

RUNTIME: {report['runtime_minutes']:.0f} minutes
TOTAL COST: ${report['unified']['total_cost']:.6f} (${report['unified']['cost_per_min']:.8f}/min)
TOTAL REVENUE: ${report['unified']['total_revenue']:.6f} (${report['unified']['revenue_per_min']:.8f}/min)
TOTAL PROFIT: ${report['unified']['total_profit']:.6f} (${report['unified']['profit_per_min']:.8f}/min)

DEPARTMENTS:
{chr(10).join(dept_lines)}

Provide a brief executive review covering:
1. Overall financial health (profitable/breakeven/subsidized)
2. Top 2 departments by profit margin
3. Bottom 2 departments by cost efficiency
4. 3 actionable recommendations to improve profitability
5. Risk assessment (what could go wrong)
6. A one-sentence summary

Be concise, data-driven, and blunt."""
    try:
        if GEMINI_API_KEY:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
            resp = requests.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 600}
            }, timeout=15)
            if resp.status_code == 200:
                cands = resp.json().get("candidates", [])
                if cands:
                    return cands[0]["content"]["parts"][0]["text"]
    except Exception:
        pass
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": "nullstate", "prompt": prompt,
                  "temperature": 0.2, "max_tokens": 600, "stream": False},
            timeout=60
        )
        if resp.status_code == 200:
            return resp.json().get("response", "AI review unavailable")
    except Exception:
        pass
    return "AI review unavailable"


def show_reports(limit: int = 5):
    """Display latest unified reports."""
    conn = get_db()
    rows = conn.execute(
        "SELECT report_id, total_cost, total_revenue, total_profit, profit_per_min, "
        "departments_ok, departments_degraded, departments_down, summary, timestamp "
        "FROM unified_reports ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    if not rows:
        print("No reports yet.")
        return
    print(f"\n{'Report ID':<30} {'Cost':<12} {'Revenue':<12} {'Profit':<12} {'$/min':<12} {'Depts':<20} {'Time'}")
    print("-" * 120)
    for r in rows:
        dept_str = f"{r['departments_ok']}OK/{r['departments_degraded']}deg/{r['departments_down']}down"
        print(f"{r['report_id']:<30} ${r['total_cost']:<8.6f} ${r['total_revenue']:<8.6f} "
              f"${r['total_profit']:<8.6f} ${r['profit_per_min']:<10.8f} {dept_str:<20} {r['timestamp'][:19]}")


def show_departments(report_id: str = ""):
    """Display department breakdown for a report."""
    conn = get_db()
    if report_id:
        rows = conn.execute(
            "SELECT * FROM department_reports WHERE report_id = ? ORDER BY cost_usdc DESC", (report_id,)
        ).fetchall()
    else:
        latest = conn.execute("SELECT MAX(id), report_id FROM unified_reports").fetchone()
        if not latest or not latest[0]:
            print("No reports yet.")
            return
        rows = conn.execute(
            "SELECT * FROM department_reports WHERE report_id = ? ORDER BY cost_usdc DESC",
            (latest[1],)
        ).fetchall()
    conn.close()
    if not rows:
        print(f"No departments found for report: {report_id or 'latest'}")
        return
    print(f"\n{'Department':<22} {'Cost':<12} {'Revenue':<12} {'Profit':<12} {'Margin':<10} {'$/min':<14} {'Status':<12}")
    print("-" * 100)
    for r in rows:
        print(f"{r['name']:<22} ${r['cost_usdc']:<8.6f} ${r['revenue_usdc']:<8.6f} "
              f"${r['profit_usdc']:<8.6f} {r['margin_pct']:<8.2f}% ${r['profit_per_min']:<10.8f} {r['status']:<12}")


def continuous(minutes: int = 60):
    """Run continuous reporting every N minutes."""
    log.info(f"Continuous 360 reporting: every {minutes} min")
    while True:
        report = run_360_report()
        review = review_reports(report)
        print(f"\n--- AI Review ---\n{review}\n---")
        time.sleep(minutes * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="NullState 360-Degree Department Reporting")
    parser.add_argument("--report", action="store_true", help="Generate one 360 report")
    parser.add_argument("--review", action="store_true", help="Generate report + AI review")
    parser.add_argument("--show", type=int, default=0, help="Show last N reports")
    parser.add_argument("--departments", type=str, default="", help="Show departments for report_id (or 'latest')")
    parser.add_argument("--continuous", type=float, default=0, help="Continuous reporting interval in minutes")
    args = parser.parse_args()

    if args.show:
        show_reports(args.show)
        return

    if args.departments:
        show_departments(args.departments if args.departments != "latest" else "")
        return

    if args.continuous:
        continuous(int(args.continuous))
        return

    report = run_360_report()

    if args.review:
        review = review_reports(report)
        print(f"\n{'='*60}")
        print("AI EXECUTIVE REVIEW")
        print(f"{'='*60}")
        print(review)

    print(f"\n{'='*60}")
    print("UNIFIED P&L")
    print(f"{'='*60}")
    u = report["unified"]
    print(f"  Runtime:     {report['runtime_minutes']:.0f} minutes")
    print(f"  Cost:        ${u['total_cost']:.6f}  (${u['cost_per_min']:.8f}/min)")
    print(f"  Revenue:     ${u['total_revenue']:.6f}  (${u['revenue_per_min']:.8f}/min)")
    print(f"  Profit:      ${u['total_profit']:.6f}  (${u['profit_per_min']:.8f}/min)")
    print("  Departments: ", end="")
    dept_summary = defaultdict(int)
    for d in report["departments"]:
        dept_summary[d["status"]] += 1
    print(", ".join(f"{v} {k}" for k, v in dept_summary.items()))

    print(f"\n{'Department':<22} {'Cost':<12} {'Rev':<12} {'Profit':<12} {'Margin':<10} {'Status':<12}")
    print("-" * 80)
    for d in report["departments"]:
        print(f"{d['name']:<22} ${d['cost_usdc']:<8.6f} ${d['revenue_usdc']:<8.6f} "
              f"${d['profit_usdc']:<8.6f} {d['margin_pct']:<8.2f}% {d['status']:<12}")


if __name__ == "__main__":
    main()

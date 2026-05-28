"""NullState Finance/BDM Autonomous Subagent — HOD v3 Module.
Monitors all revenue streams, optimizes pricing, provisions resources,
and executes revenue-generating actions autonomously.

Runs as a sub-cycle within the daemon loop or standalone via:
    python3 -m finance_bdm.subagent [--cycle] [--report]
"""

import os
import json
import time
import uuid
import sqlite3
import logging
import subprocess
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [FINANCE] %(message)s")
log = logging.getLogger("nullstate-finance")

SRC_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("NULLSTATE_DB_PATH", str(SRC_DIR / "core" / "nullstate.db"))
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "https://localhost:8080")
MODEL_API_URL = os.environ.get("MODEL_API_URL", "http://localhost:8082")
BACKUP_DIR = SRC_DIR.parent / "backups"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS finance_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT,
            agent_id TEXT,
            amount REAL,
            gateway TEXT,
            status TEXT DEFAULT 'pending',
            result TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS revenue_streams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stream_name TEXT UNIQUE,
            revenue_ytd REAL DEFAULT 0,
            revenue_30d REAL DEFAULT 0,
            revenue_7d REAL DEFAULT 0,
            cost_30d REAL DEFAULT 0,
            margin_pct REAL DEFAULT 0,
            active_customers INTEGER DEFAULT 0,
            last_payment TEXT,
            last_updated TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS bdm_opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            opportunity_type TEXT,
            description TEXT,
            estimated_value REAL,
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'open',
            action_taken TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


def call_ai(prompt: str, max_tokens: int = 400) -> Optional[str]:
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": os.environ.get("NULLSTATE_MODEL", "nullstate"),
                  "prompt": prompt, "temperature": 0.2,
                  "max_tokens": max_tokens, "stream": False},
            timeout=60
        )
        if resp.status_code == 200:
            return resp.json().get("response")
    except Exception as e:
        log.warning("AI call failed: %s", e)
    return None


def query_revenue_streams() -> dict:
    """Query all revenue sources and return current state."""
    streams = {}
    try:
        conn = get_db()
        rows = conn.execute("""
            SELECT stream_name, revenue_7d, revenue_30d, revenue_ytd, cost_30d, margin_pct, active_customers
            FROM revenue_streams ORDER BY revenue_30d DESC
        """).fetchall()
        for r in rows:
            streams[r["stream_name"]] = dict(r)
        conn.close()
    except Exception as e:
        log.warning("revenue streams query: %s", e)
    return streams


def compute_revenue_metrics() -> dict:
    """Compute revenue from ledger + billing tables."""
    metrics = {"total_revenue": 0.0, "gateway_fees": 0.0, "model_api": 0.0,
               "email_relay": 0.0, "prepaid_credits": 0.0, "tasks_processed": 0, "active_agents": 0}
    try:
        conn = get_db()
        ledger = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM ledger WHERE verified=1").fetchone()[0] or 0
        metrics["total_revenue"] = round(ledger, 4)

        api_usage = conn.execute("SELECT COALESCE(SUM(cost), 0) FROM api_usage").fetchone()[0] or 0
        metrics["model_api"] = round(api_usage, 4)

        credit_total = conn.execute("SELECT COALESCE(SUM(balance_usdc), 0) FROM credits").fetchone()[0] or 0
        lifetime = conn.execute("SELECT COALESCE(SUM(lifetime_deposits), 0) FROM credits").fetchone()[0] or 0
        metrics["prepaid_credits"] = round(credit_total, 4)
        metrics["lifetime_deposits"] = round(lifetime, 4)

        task_count = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='completed'").fetchone()[0] or 0
        metrics["tasks_processed"] = task_count

        agent_count = conn.execute("SELECT COUNT(DISTINCT agent_id) FROM credits").fetchone()[0] or 0
        metrics["active_agents"] = agent_count

        billing = conn.execute("SELECT product, COALESCE(SUM(total_usdc), 0) as rev FROM billing_ledger GROUP BY product").fetchall()
        for b in billing:
            metrics[b["product"]] = round(b["rev"], 4)

        conn.close()
    except Exception as e:
        log.warning("metrics error: %s", e)
    return metrics


def record_revenue_stream(stream_name: str, amount: float, active_customers: int = 0, cost: float = 0):
    """Update rolling revenue for a stream."""
    try:
        conn = get_db()
        margin = ((amount - cost) / amount * 100) if amount > 0 else 0
        conn.execute("""
            INSERT INTO revenue_streams (stream_name, revenue_7d, revenue_30d, revenue_ytd, cost_30d, margin_pct, active_customers, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(stream_name) DO UPDATE SET
                revenue_7d = revenue_7d + ?,
                revenue_30d = revenue_30d + ?,
                revenue_ytd = revenue_ytd + ?,
                cost_30d = cost_30d + ?,
                margin_pct = ?,
                active_customers = ?,
                last_updated = datetime('now')
        """, (stream_name, amount, amount, amount, cost, margin, active_customers,
              amount, amount, amount, cost, margin, active_customers))
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("record stream error: %s", e)


def log_action(action_type: str, agent_id: str, amount: float, gateway: str, status: str = "completed", result: str = ""):
    try:
        conn = get_db()
        conn.execute("INSERT INTO finance_actions (action_type, agent_id, amount, gateway, status, result) VALUES (?,?,?,?,?,?)",
                     (action_type, agent_id, amount, gateway, status, result))
        conn.commit()
        conn.close()
    except Exception:
        pass


def find_pricing_opportunities(metrics: dict) -> list[dict]:
    """Use AI to identify pricing and revenue optimization opportunities."""
    prompt = f"""You are the NullState Finance/BDM subagent. Analyze these revenue metrics and identify 2-3 specific pricing or revenue optimization opportunities.

Current Metrics:
- Total revenue (ledger): ${metrics.get('total_revenue', 0):.4f}
- Model API revenue: ${metrics.get('model_api', 0):.4f}
- Prepaid credits total: ${metrics.get('prepaid_credits', 0):.4f}
- Lifetime deposits: ${metrics.get('lifetime_deposits', 0):.4f}
- Tasks processed: {metrics.get('tasks_processed', 0)}
- Active agents: {metrics.get('active_agents', 0)}

Products:
- solution_api: $0.025/request
- model_inference: $0.0005/1K tokens
- email_relay: $5.00/1000 emails
- Subscriptions: Free(5/mo), Scout($50/500), Pro($200/5000), Enterprise($500/99999)

Return a JSON array of opportunities, each with: opportunity_type, description, suggested_action, estimated_monthly_value, priority (high/medium/low)"""

    result = call_ai(prompt)
    if result:
        try:
            json_start = result.find("[")
            json_end = result.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(result[json_start:json_end])
        except (json.JSONDecodeError, ValueError):
            pass

    return [{"opportunity_type": "pricing_review", "description": "Manual review of pricing tiers vs market", "suggested_action": "Review competitor pricing", "estimated_monthly_value": 0, "priority": "low"}]


def create_api_key_for_client(client_name: str, budget: float = 50.0) -> dict:
    """Provision a new agent API key and auto-credit."""
    agent_id = f"client_{uuid.uuid4().hex[:12]}"
    api_key = hashlib.sha256(f"ns_key_{agent_id}_{int(time.time())}".encode()).hexdigest()[:32]

    from core.billing import add_credits
    try:
        add_credits(agent_id, budget, f"provision_{client_name}")
        log.info("Provisioned %s with $%.2f credits (key: %s...) — client: %s", agent_id, budget, api_key[:8], client_name)
        log_action("provision", agent_id, budget, "internal")
        record_revenue_stream("client_provisioning", budget, active_customers=1)
        return {"agent_id": agent_id, "api_key": api_key, "initial_balance": budget, "client_name": client_name}
    except Exception as e:
        log.error("provision error: %s", e)
        return {"error": str(e)}


def generate_sales_report() -> str:
    """Generate a summary of all revenue streams and opportunities."""
    metrics = compute_revenue_metrics()
    streams = query_revenue_streams()
    report = []
    report.append("=" * 60)
    report.append(f"NullState Finance Report — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    report.append("=" * 60)
    report.append(f"Total Ledger Revenue: ${metrics['total_revenue']:.4f}")
    report.append(f"Lifetime Deposits:   ${metrics.get('lifetime_deposits', 0):.4f}")
    report.append(f"Model API Revenue:   ${metrics['model_api']:.4f}")
    report.append(f"Tasks Processed:     {metrics['tasks_processed']}")
    report.append(f"Active Agents:       {metrics['active_agents']}")
    report.append("")
    report.append("--- Revenue Streams ---")
    for name, data in streams.items():
        report.append(f"  {name}: ${data.get('revenue_30d', 0):.4f} (30d) | margin: {data.get('margin_pct', 0):.1f}% | customers: {data.get('active_customers', 0)}")
    report.append("")
    report.append("--- Product Pricing ---")
    from core.billing import PRODUCTS
    for sku, info in PRODUCTS.items():
        report.append(f"  {sku}: ${info['price_per_unit']:.4f} per {info['unit']}")
    report.append("")
    report.append("--- Payment Gateways ---")
    from core.payment_gateways import available_gateways
    for g in available_gateways():
        report.append(f"  {g['label']}: fees {g['fee_pct']}% + ${g['fee_fixed']:.2f}")
    report.append("")
    opportunities = find_pricing_opportunities(metrics)
    report.append("--- AI-Identified Opportunities ---")
    for opp in opportunities:
        report.append(f"  [{opp.get('priority', 'low').upper()}] {opp.get('opportunity_type', 'n/a')}: {opp.get('description', '')}")
        report.append(f"    → {opp.get('suggested_action', '')} (est. ${opp.get('estimated_monthly_value', 0):.2f}/mo)")
    report.append("=" * 60)
    return "\n".join(report)


def cycle():
    """Main subagent cycle — runs every daemon loop iteration."""
    log.info("=== Finance/BDM Subagent Cycle ===")

    metrics = compute_revenue_metrics()
    log.info("Revenue: ledger=$%.4f | model_api=$%.4f | credits=$%.4f | tasks=%d | agents=%d",
             metrics["total_revenue"], metrics["model_api"], metrics["prepaid_credits"],
             metrics["tasks_processed"], metrics["active_agents"])

    record_revenue_stream("model_inference", metrics.get("model_api", 0), metrics.get("active_agents", 0))

    opportunities = find_pricing_opportunities(metrics)
    for opp in opportunities:
        try:
            conn = get_db()
            conn.execute("""
                INSERT INTO bdm_opportunities (source, opportunity_type, description, estimated_value, priority, status)
                VALUES (?, ?, ?, ?, ?, 'open')
            """, ("ai_agent", opp.get("opportunity_type", ""), opp.get("description", ""),
                  opp.get("estimated_monthly_value", 0), opp.get("priority", "medium")))
            conn.commit()
            conn.close()
        except Exception:
            pass
        if opp.get("priority") == "high":
            log.info("HIGH PRIORITY OPPORTUNITY: %s — %s", opp["opportunity_type"], opp["description"])

    log.info("Finance/BDM cycle complete — %d metrics, %d opportunities", len(metrics), len(opportunities))
    return metrics


if __name__ == "__main__":
    import sys
    import hashlib
    if "--report" in sys.argv:
        print(generate_sales_report())
    elif "--cycle" in sys.argv:
        cycle()
    else:
        print(generate_sales_report())

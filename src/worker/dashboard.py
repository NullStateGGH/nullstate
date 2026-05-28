"""NullState Gateway Dashboard — Live analytics from SQLite telemetry.

Serves a real-time HTML dashboard at /dashboard on the gateway.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DASHBOARD_PATH = Path("/home/Nullstate-linux-vm/nullstate-website/static/dashboard.html")
TELEMETRY_DB = Path("/home/Nullstate-linux-vm/src/core/telemetry.db")
GATEWAY_DB = Path("/home/Nullstate-linux-vm/src/core/nullstate.db")


def get_db(db_path):
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def generate_dashboard():
    """Generate static dashboard HTML from telemetry data."""

    # Get gateway stats
    gw = get_db(GATEWAY_DB)
    task_count = 0
    ledger_count = 0
    balance = 0.0

    if gw:
        try:
            task_count = gw.execute("SELECT COUNT(*) as c FROM tasks").fetchone()["c"]
        except Exception:
            pass
        try:
            ledger_count = gw.execute("SELECT COUNT(*) as c FROM ledger").fetchone()["c"]
        except Exception:
            pass
        try:
            balance = gw.execute("SELECT COALESCE(SUM(amount),0) as s FROM ledger").fetchone()["s"]
        except Exception:
            pass
        gw.close()

    # Get telemetry stats
    tel = get_db(TELEMETRY_DB)
    interactions = 0
    avg_score = 0.0
    scored = 0
    recent = []

    if tel:
        try:
            interactions = tel.execute("SELECT COUNT(*) as c FROM interactions").fetchone()["c"]
        except Exception:
            pass
        try:
            row = tel.execute("SELECT COALESCE(AVG(score),0) as s FROM quality_scores").fetchone()
            avg_score = row["s"]
        except Exception:
            pass
        try:
            scored = tel.execute("SELECT COUNT(*) as c FROM quality_scores").fetchone()["c"]
        except Exception:
            pass
        try:
            rows = tel.execute(
                "SELECT action, model_used, latency_ms, success, revenue_stream, amount_usdc, protocol, created_at "
                "FROM interactions ORDER BY created_at DESC LIMIT 10"
            ).fetchall()
            recent = [dict(r) for r in rows]
        except Exception:
            pass
        tel.close()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NullState — Live Dashboard</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#030303; color:#e6edf3; font-family:'Inter',system-ui,sans-serif; padding:2rem; }}
  .container {{ max-width:1200px; margin:0 auto; }}
  h1 {{ font-size:2rem; font-weight:700; margin-bottom:0.5rem; color:#00ff9d; }}
  h1 small {{ font-size:1rem; color:#666; font-weight:400; }}
  .subtitle {{ color:#666; margin-bottom:2rem; font-size:0.9rem; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:1rem; margin-bottom:2rem; }}
  .card {{ background:#080808; border:1px solid #1a1a1a; border-radius:12px; padding:1.5rem; }}
  .card .label {{ font-size:0.75rem; text-transform:uppercase; letter-spacing:0.1em; color:#666; margin-bottom:0.5rem; }}
  .card .value {{ font-size:2rem; font-weight:700; color:#e6edf3; }}
  .card .value.green {{ color:#00ff9d; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ text-align:left; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.1em; color:#666; padding:0.75rem 0.5rem; border-bottom:1px solid #1a1a1a; }}
  td {{ padding:0.75rem 0.5rem; border-bottom:1px solid #111; font-size:0.85rem; }}
  .ok {{ color:#00ff9d; }}
  .fail {{ color:#ff4444; }}
  footer {{ margin-top:3rem; padding-top:1.5rem; border-top:1px solid #1a1a1a; color:#666; font-size:0.8rem; }}
  .updated {{ color:#00ff9d; font-size:0.75rem; }}
</style>
</head>
<body>
<div class="container">
  <h1>/dashboard <small>⚡</small></h1>
  <div class="subtitle">NullState Gateway — Live Telemetry &amp; Metrics</div>

  <div class="grid">
    <div class="card">
      <div class="label">Tasks Processed</div>
      <div class="value green">{task_count}</div>
    </div>
    <div class="card">
      <div class="label">Ledger Entries</div>
      <div class="value green">{ledger_count}</div>
    </div>
    <div class="card">
      <div class="label">Balance (USDC)</div>
      <div class="value green">${balance:.2f}</div>
    </div>
    <div class="card">
      <div class="label">Interactions Recorded</div>
      <div class="value green">{interactions}</div>
    </div>
    <div class="card">
      <div class="label">Quality Scored</div>
      <div class="value">{scored}</div>
    </div>
    <div class="card">
      <div class="label">Avg Quality Score</div>
      <div class="value">{avg_score:.1f}/5</div>
    </div>
  </div>

  <h2 style="font-size:1.2rem; margin-bottom:1rem; color:#e6edf3;">Recent Interactions</h2>
  <table>
    <thead>
      <tr><th>Action</th><th>Model</th><th>Latency</th><th>Status</th><th>Revenue</th><th>Protocol</th><th>Time</th></tr>
    </thead>
    <tbody>
"""
    for r in recent:
        status = '<span class="ok">✓</span>' if r.get("success") else '<span class="fail">✗</span>'
        html += f"      <tr><td>{r.get('action','')[:30]}</td><td>{r.get('model_used','')[:20]}</td><td>{r.get('latency_ms',0)}ms</td><td>{status}</td><td>${r.get('amount_usdc',0):.4f}</td><td>{r.get('protocol','')[:10]}</td><td>{str(r.get('created_at',''))[:19]}</td></tr>\n"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    html += f"""    </tbody>
  </table>

  <footer>
    <span class="updated">● live</span> — Last updated: {now}<br>
    <a href="https://greensol.me/nullstate" style="color:#00ff9d;">← back to NullState</a>
  </footer>
</div>
</body>
</html>"""

    DASHBOARD_PATH.write_text(html)
    print(f"[dashboard] Generated at {DASHBOARD_PATH}")
    return html


if __name__ == "__main__":
    generate_dashboard()

"""
NullState Autonomous Daemon v2 — AI-driven self-orchestration.

Self-orchestrates: crawler, processor, revenue streams, heartbeat, health checks.
Self-heals: restarts failed subprocesses, auto-recover from crashes.
Multi-revenue: cycles through gateway fees, MCP licensing, KYA certs, extensions.
"""

import json
import os
import signal
import subprocess
import sys
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config
from core.log import setup
from core.database import get_db

log = setup("daemon")

DAEMON_DIR = Path(__file__).resolve().parent.parent
CRAWLER = DAEMON_DIR / "agents" / "crawler.py"
PROCESSOR = DAEMON_DIR / "worker" / "processor.py"
GATEWAY = DAEMON_DIR / "network" / "gateway.py"
MCP = DAEMON_DIR / "network" / "mcp_server.py"
HUB = DAEMON_DIR / "extensions" / "mcp-hub" / "hub.py"
GITHUB = DAEMON_DIR / "extensions" / "github" / "server.py"
BACKUP_SCRIPT = DAEMON_DIR / "core" / "store.py"

_running = True
_subprocs: dict[str, subprocess.Popen] = {}
_health = {
    "cycle": 0,
    "started": datetime.now(timezone.utc).isoformat(),
    "crawler_ok": False,
    "processor_ok": False,
    "gateway_ok": False,
    "mcp_ok": False,
    "hub_ok": False,
    "github_ok": False,
    "tasks_processed": 0,
    "total_revenue": 0.0,
    "last_crawl": None,
    "last_process": None,
    "errors": [],
}
_errors: list[str] = []
MAX_ERRORS = 50


def _shutdown(signum, frame):
    global _running
    log.info("received signal %d — shutting down all subprocesses", signum)
    _running = False
    for name, proc in _subprocs.items():
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


for sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(sig, _shutdown)


def run_script(path: Path, label: str, timeout: int = 120) -> bool:
    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        for line in result.stdout.splitlines():
            log.info("[%s] %s", label, line)
        if result.stderr:
            for line in result.stderr.splitlines():
                log.warning("[%s][stderr] %s", label, line)
        if result.returncode != 0:
            log.warning("%s exited code %d", label, result.returncode)
            _record_error(f"{label} exited {result.returncode}")
            return False
        return True
    except subprocess.TimeoutExpired:
        log.warning("%s timed out (%ds)", label, timeout)
        _record_error(f"{label} timeout")
        return False
    except Exception as e:
        log.error("%s failed — %s", label, e)
        _record_error(f"{label}: {e}")
        return False


def _record_error(msg: str):
    _errors.append(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")
    if len(_errors) > MAX_ERRORS:
        _errors.pop(0)


def open_count() -> int:
    return get_db().count_open_tasks()


def ai_scored_count() -> int:
    return get_db().count_ai_scored_tasks()


def total_revenue() -> float:
    return get_db().get_ledger_balance()


def self_heal(service_name: str, path: Path) -> bool:
    """Restart a subprocess if it's not running."""
    if service_name in _subprocs:
        proc = _subprocs[service_name]
        if proc.poll() is None:
            return True  # still running
        log.warning("%s died — restarting", service_name)
    try:
        proc = subprocess.Popen(
            [sys.executable, str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _subprocs[service_name] = proc
        log.info("%s started (pid %d)", service_name, proc.pid)
        return True
    except Exception as e:
        log.error("failed to start %s — %s", service_name, e)
        _record_error(f"self-heal {service_name}: {e}")
        return False


def ai_orchestrate() -> dict:
    """AI-driven orchestration decision: what to run next."""
    db = get_db()
    tasks = db.get_tasks()
    open_tasks = [t for t in tasks if t.get("status") == "open"]
    scored_count = ai_scored_count()
    revenue = total_revenue()

    decision = {
        "should_crawl": len(open_tasks) < 20,
        "should_process": len(open_tasks) > 0,
        "should_backup": True,
        "should_harvest": True,
    }

    if len(open_tasks) > 50:
        decision["crawl_priority"] = "low"
        decision["process_priority"] = "high"
    elif len(open_tasks) > 10:
        decision["crawl_priority"] = "medium"
        decision["process_priority"] = "high"
    else:
        decision["crawl_priority"] = "high"
        decision["process_priority"] = "medium"

    if scored_count > 5 and revenue > 1.0:
        decision["revenue_momentum"] = "high"
    elif revenue > 0.1:
        decision["revenue_momentum"] = "medium"
    else:
        decision["revenue_momentum"] = "low"

    log.info("orchestrate: %d open, %d ai-scored, $%.4f revenue",
             len(open_tasks), scored_count, revenue)
    return decision


def auto_backup():
    """Auto-backup database and state files."""
    import shutil
    from core.store import atomic_read, atomic_write
    _db = get_db()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = config.PATHS["backups"]
    try:
        db_path = config.PATHS["db"]
        if db_path.exists():
            shutil.copy2(db_path, backup_dir / f"nullstate_db_{ts}.db")
        log.info("auto-backup complete — %s", ts)
    except Exception as e:
        log.warning("auto-backup failed — %s", e)


def revenue_harvest():
    """Cycle through all revenue streams and record metrics."""
    db = get_db()
    total = total_revenue()

    streams = {
        "gateway_fees": sum(
            e.get("amount", 0) for e in db.get_ledger()
            if "gateway" in e.get("source", "").lower()
        ),
        "mcp_tools": sum(
            e.get("amount", 0) for e in db.get_ledger()
            if "mcp" in e.get("source", "").lower()
        ),
        "extensions": sum(
            e.get("amount", 0) for e in db.get_ledger()
            if "vscode" in e.get("source", "").lower()
            or "chrome" in e.get("source", "").lower()
            or "cli" in e.get("source", "").lower()
        ),
        "kya_certs": sum(
            e.get("amount", 0) for e in db.get_ledger()
            if "kya" in e.get("source", "").lower()
        ),
    }

    log.info("revenue harvest — total: $%.6f | gateway: $%.6f | mcp: $%.6f | ext: $%.6f | kya: $%.6f",
             total, streams["gateway_fees"], streams["mcp_tools"],
             streams["extensions"], streams["kya_certs"])

    _health["total_revenue"] = total
    return streams


def _harvest_instant_revenue():
    """Harvest from instant income streams: billing credits, model API, email relay."""
    try:
        from core.billing import get_credits, list_products
        total_credits = 0.0
        conn = get_db().conn
        rows = conn.execute("SELECT agent_id, balance_usdc FROM credits").fetchall()
        for r in rows:
            total_credits += r["balance_usdc"]
        model_usage = conn.execute("SELECT COALESCE(SUM(cost), 0) FROM api_usage").fetchone()[0] or 0.0
        log.info("instant revenue — credits: $%.4f | model api: $%.4f | total_ledger: $%.4f",
                 total_credits, model_usage, total_revenue())
    except Exception as e:
        log.warning("instant revenue harvest error: %s", e)


def heartbeat():
    """Log health metrics to system."""
    _health["tasks_processed"] = sum(
        1 for t in get_db().get_tasks() if t.get("status") == "completed"
    )
    _health["errors"] = _errors[-10:]
    log.info("heartbeat — cycle %d | tasks: %d open / %d processed | revenue: $%.4f | errors: %d",
             _health["cycle"],
             open_count(),
             _health["tasks_processed"],
             total_revenue(),
             len(_errors))


def immortal_loop() -> None:
    global _subprocs

    log.info("NullState Autonomous Daemon v2 — self-orchestrating, self-healing")
    cycle = 0
    last_backup = 0
    heartbeat_interval = config.HEARTBEAT_INTERVAL
    last_heartbeat = 0

    while _running:
        cycle += 1
        _health["cycle"] = cycle
        log.info("=== CYCLE %d ===", cycle)

        # 1. Self-heal income-generating services
        self_heal("gateway", GATEWAY)
        self_heal("mcp", MCP)
        self_heal("hub", HUB)

        # 2. Process existing tasks only (no new crawling)
        open_tasks = open_count()
        if open_tasks > 0:
            adaptive_sleep = max(5, min(30, 30 - ai_scored_count() * 3))
            log.info("%d open tasks — processing in %ds", open_tasks, adaptive_sleep)
            _interruptible_sleep(adaptive_sleep)
            if not _running:
                break
            ok = run_script(PROCESSOR, "processor", timeout=120)
            _health["processor_ok"] = ok
            _health["last_process"] = datetime.now(timezone.utc).isoformat()
        else:
            log.info("0 pending tasks — no processing needed")

        # 3. Auto-backup (every 20 cycles)
        if cycle - last_backup >= 20:
            auto_backup()
            last_backup = cycle

        # 4. Telemetry cycle
        telemetry_cycle()

        # 5. Finance/BDM subagent cycle
        try:
            from finance_bdm.subagent import cycle as finance_cycle
            finance_cycle()
        except Exception as e:
            log.warning("finance subagent error: %s", e)

        # 6. Revenue harvest & growth
        revenue_harvest()
        _harvest_instant_revenue()

        # 6. Heartbeat
        if time.time() - last_heartbeat >= heartbeat_interval:
            heartbeat()
            last_heartbeat = time.time()

        # 7. Adaptive sleep (revenue-focused cycle)
        sleep_time = 120  # 2min cycle — fast revenue check
        log.info("cycle %d complete — sleeping %ds", cycle, sleep_time)
        _interruptible_sleep(sleep_time)

    log.info("daemon stopped — %d cycles | $%.4f revenue", cycle, total_revenue())


def _interruptible_sleep(seconds: int) -> None:
    for _ in range(seconds):
        if not _running:
            break
        time.sleep(1)


# ─── Telemetry Integration ───────────────────────────────────────────────
from worker.telemetry import (
    init_db as telemetry_init_db,
    record_interaction,
    score_pending_interactions,
    export_training_data,
    upload_to_gcs,
)

TELEMETRY_INTERVAL = 300  # score every 5 min
EXPORT_INTERVAL = 3600     # export every hour
_last_telemetry_score = 0
_last_telemetry_export = 0

def telemetry_cycle():
    global _last_telemetry_score, _last_telemetry_export
    api_key = os.environ.get("NULLSTATE_GOOGLE_API_KEY", "")
    now = time.time()

    # Seed a few sample interactions per cycle for demonstration
    try:
        record_interaction(
            agent_id="daemon",
            action="orchestrate",
            prompt=f"cycle={_health['cycle']}, open_tasks={open_count()}, revenue={total_revenue():.4f}",
            response=json.dumps(ai_orchestrate()),
            model_used="heuristic",
            latency_ms=0,
            success=True,
            revenue_stream="system",
            amount_usdc=total_revenue(),
            protocol="internal",
        )
    except Exception:
        pass

    # Score pending interactions
    if now - _last_telemetry_score >= TELEMETRY_INTERVAL and api_key:
        try:
            scored = score_pending_interactions(api_key, batch_size=10)
            if scored:
                log.info("[telemetry] scored %d interactions", scored)
            _last_telemetry_score = now
        except Exception as e:
            log.warning("[telemetry] scoring error: %s", e)

    # Export and upload training data
    if now - _last_telemetry_export >= EXPORT_INTERVAL:
        try:
            exported = export_training_data(limit=200)
            if exported:
                local_path, gcs_path, count = exported
                ok = upload_to_gcs(local_path, gcs_path)
                log.info("[telemetry] exported %d records → gs://%s/%s (ok=%s)",
                         count, "nullstate-press", gcs_path, ok)
            _last_telemetry_export = now
        except Exception as e:
            log.warning("[telemetry] export error: %s", e)


if __name__ == "__main__":
    immortal_loop()

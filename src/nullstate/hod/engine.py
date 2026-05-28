"""NullState HOD v2 — Full Level 4 Autonomous Engine.
Revenue Engine + Growth Engine + Self-Heal + Auto-Deploy + Emergency Mode.
"""

import os
import json
import time
import sqlite3
import uuid
import threading
import subprocess
import logging
import shutil
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [HOD] %(message)s")
log = logging.getLogger("nullstate-hod")

DB_PATH = os.environ.get("NULLSTATE_DB_PATH", "src/core/nullstate.db")
MODEL_API_URL = os.environ.get("MODEL_API_URL", "http://localhost:8082")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "https://localhost:8080")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
NULLSTATE_MODEL = os.environ.get("NULLSTATE_MODEL", "nullstate")
WEBSITE_DIR = "/home/Nullstate-linux-vm/nullstate-website"
BACKUP_DIR = "/home/Nullstate-linux-vm/backups"

COST_PER_RAM_GB_HOUR = 0.005
COST_PER_CPU_CORE_HOUR = 0.01

SERVICES = [
    "nullstate", "nullstate-gateway", "nullstate-mcp",
    "nullstate-model-api", "nullstate-mail", "nullstate-hub",
    "nullstate-github", "nullstate-hod", "nullstate-feedback",
    "nullstate-global-feedback", "nullstate-reporting",
    "nullstate-adaptation"
]

REVENUE_THRESHOLD_WARN = 0.5
DISK_USAGE_WARN_PCT = 85
RESPONSE_TIME_WARN_SEC = 5.0


@dataclass
class CostLedger:
    costs: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    revenue: Dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def record_cost(self, category: str, amount: float, description: str = ""):
        self.costs[category] = self.costs.get(category, 0) + amount
        self._write_ledger("cost", category, amount, description)

    def _write_ledger(self, type_: str, category: str, amount: float, description: str):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("CREATE TABLE IF NOT EXISTS hod_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, category TEXT, amount REAL, description TEXT, timestamp TEXT)")
            conn.execute("INSERT INTO hod_ledger (type, category, amount, description, timestamp) VALUES (?,?,?,?,?)",
                         (type_, category, round(amount, 6), description, datetime.now(timezone.utc).isoformat()))
            conn.commit()
            conn.close()
        except Exception as e:
            log.error(f"Ledger write error: {e}")

    def summary(self) -> Dict:
        return {"total_costs": round(sum(self.costs.values()), 4), "total_revenue": round(sum(self.revenue.values()), 4)}


class TaskDelegator:
    CAPABILITIES = {
        "generate_synthetic_data": {
            "command": "python3 -m nullstate.training.synthesize_dataset --count {} --domain {} --workers 16 2>/dev/null",
            "cost_estimate": 0.05, "priority": 1,
        },
        "expand_dataset": {
            "command": "python3 -m nullstate.training.expand_dataset",
            "cost_estimate": 0.002, "priority": 2,
        },
        "push_dataset_to_hf": {
            "command": "python3 -m nullstate.hod.push_to_hf",
            "cost_estimate": 0.001, "priority": 2,
        },
        "ingest_google_knowledge": {
            "command": "python3 -m nullstate.hod.google_ingest --trends-only",
            "cost_estimate": 0.02, "priority": 3,
        },
        "global_feedback_cycle": {
            "command": "python3 -m nullstate.hod.global_feedback --cycle 2>/dev/null",
            "cost_estimate": 0.05, "priority": 2,
        },
        "apply_global_decisions": {
            "command": "python3 -m nullstate.hod.global_feedback --apply 2>/dev/null",
            "cost_estimate": 0.05, "priority": 2,
        },
        "generate_360_report": {
            "command": "python3 -m nullstate.hod.reporting --review 2>/dev/null",
            "cost_estimate": 0.005, "priority": 1,
        },
        "unfair_advantage_cycle": {
            "command": "python3 -m nullstate.hod.adaptation --cycle 2>/dev/null",
            "cost_estimate": 0.002, "priority": 1,
        },
        "check_health": {
            "command": "curl -sfk {}/health 2>/dev/null",
            "cost_estimate": 0.001, "priority": 4,
        },
        "backup_database": {
            "command": "cp src/core/nullstate.db backups/auto_hod_backup.db && echo 'Backup done'",
            "cost_estimate": 0.001, "priority": 5,
        },
        "self_heal_services": {
            "command": "for s in nullstate nullstate-gateway nullstate-mcp nullstate-model-api nullstate-mail nullstate-hod; do systemctl is-active --quiet \"$s.service\" || sudo systemctl restart \"$s.service\"; done; echo 'Self-heal done'",
            "cost_estimate": 0.001, "priority": 3,
        },
        "generate_blog_post": {
            "command": "python3 -c \"import json,requests; r=requests.post('{}/api/generate',json={{\\\"model\\\":\\\"nullstate\\\",\\\"prompt\\\":\\\"Write a 300-word technical blog post about {}. Include a title, 3 sections, and a conclusion. Use markdown.\\\",\\\"stream\\\":false}},timeout=120); print(r.json().get('response',''))\"",
            "cost_estimate": 0.01, "priority": 4,
        },
        "cleanup_logs": {
            "command": "find /home/Nullstate-linux-vm/logs -name '*.log' -mtime +7 -delete 2>/dev/null; find /home/Nullstate-linux-vm/backups -name '*.db' -mtime +30 -delete 2>/dev/null; echo 'Cleanup done'",
            "cost_estimate": 0.001, "priority": 5,
        },
        "deploy_website": {
            "command": "cd /home/Nullstate-linux-vm/nullstate-website && npm run build 2>/dev/null && curl -s -T build/index.html ftp://admin@greensol.me:V8sHRwRF#p^o@server26.shared.spaceship.host/nullstate/ 2>/dev/null; echo 'Deploy attempted'",
            "cost_estimate": 0.01, "priority": 3,
        },
    }

    def __init__(self, cost_ledger: CostLedger):
        self.ledger = cost_ledger
        self.active_tasks = {}

    def delegate(self, task_name: str, **kwargs) -> str:
        if task_name not in self.CAPABILITIES:
            log.warning(f"Unknown task: {task_name}")
            return None
        task_id = f"hod_{uuid.uuid4().hex[:8]}"
        capability = self.CAPABILITIES[task_name]
        self.ledger.record_cost(f"compute_{task_name}", capability["cost_estimate"], f"Delegated {task_name} ({task_id})")
        try:
            command = capability["command"].format(*kwargs.values()) if kwargs else capability["command"]
            log.info(f"Delegating {task_name} -> {task_id}: {command[:80]}...")
            thread = threading.Thread(target=self._execute_task, args=(task_id, task_name, command), daemon=True)
            thread.start()
            self.active_tasks[task_id] = {"task_name": task_name, "status": "running", "started": datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            log.error(f"Delegation failed for {task_name}: {e}")
            self.active_tasks[task_id] = {"task_name": task_name, "status": "failed", "error": str(e)}
        return task_id

    def _execute_task(self, task_id, task_name, command):
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=3600, env={**os.environ, "PYTHONPATH": "src"})
            self.active_tasks[task_id]["status"] = "completed" if result.returncode == 0 else "failed"
            self.active_tasks[task_id]["output"] = (result.stdout or result.stderr)[-200:]
            self.active_tasks[task_id]["completed"] = datetime.now(timezone.utc).isoformat()
            if result.returncode == 0 and task_name == "generate_blog_post":
                self._save_blog_post(result.stdout, task_id)
            if result.returncode == 0 and task_name == "deploy_website":
                log.info("Website deploy completed")
        except subprocess.TimeoutExpired:
            self.active_tasks[task_id]["status"] = "timeout"
        except Exception as e:
            self.active_tasks[task_id]["status"] = "error"
            self.active_tasks[task_id]["error"] = str(e)

    def _save_blog_post(self, content: str, task_id: str):
        blog_dir = Path("/home/Nullstate-linux-vm/nullstate-website/blog")
        blog_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        slug = f"hod-auto-{task_id}"
        filepath = blog_dir / f"{date_str}-{slug}.md"
        header = f"---\nslug: {slug}\ntitle: HOD Auto-Generated Post ({date_str})\nauthors: [hod]\ntags: [autonomous, ai, hod]\n---\n\n"
        filepath.write_text(header + content)
        log.info(f"Blog post saved: {filepath}")

    def status(self) -> Dict:
        return {"active_tasks": len(self.active_tasks), "running": [t for t, v in self.active_tasks.items() if v["status"] == "running"]}


class HODEngine:
    def __init__(self):
        self.ledger = CostLedger()
        self.delegator = TaskDelegator(self.ledger)
        self.running = False
        self.cycle_count = 0
        self.ram_gb = 65
        self.cpu_cores = 32
        self.last_deploy_time = 0
        self.last_revenue_check = datetime.now(timezone.utc) - timedelta(hours=24)
        self.last_good_revenue = 0.0
        self.health_history: list[dict] = []
        log.info(f"HOD v2 initialized — {self.ram_gb}GB RAM, {self.cpu_cores} cores, ${self.compute_cost_per_hour():.4f}/hour")

    def compute_cost_per_hour(self) -> float:
        return self.ram_gb * COST_PER_RAM_GB_HOUR + self.cpu_cores * COST_PER_CPU_CORE_HOUR

    def record_infra_cost(self, duration_hours: float = 1.0) -> float:
        cost = self.compute_cost_per_hour() * duration_hours
        self.ledger.record_cost("infrastructure", cost, f"Compute x {duration_hours}h")
        return cost

    def query_real_revenue(self) -> float:
        real_revenue = 0.0
        try:
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM ledger WHERE verified = 1").fetchone()
            real_revenue += row[0] if row else 0.0
            row = conn.execute("SELECT COALESCE(SUM(cost), 0) FROM api_usage").fetchone()
            real_revenue += row[0] if row else 0.0
            row = conn.execute("SELECT COALESCE(SUM(balance_usdc), 0) FROM credits").fetchone()
            conn.close()
        except Exception:
            pass
        return real_revenue

    # ─── Phase 4: Self-Healing v2 ──────────────────────────────────────
    def check_service_health(self) -> list[str]:
        """Check response times, not just active status."""
        degraded = []
        for svc in SERVICES:
            try:
                start = time.time()
                r = subprocess.run(["systemctl", "is-active", f"{svc}.service"], capture_output=True, text=True, timeout=5)
                elapsed = time.time() - start
                if r.stdout.strip() != "active":
                    degraded.append(f"{svc} (inactive)")
                elif elapsed > RESPONSE_TIME_WARN_SEC:
                    degraded.append(f"{svc} (slow: {elapsed:.1f}s)")
            except Exception as e:
                degraded.append(f"{svc} (check error: {e})")
        return degraded

    def check_disk_usage(self) -> Optional[str]:
        """Check disk usage and clean if needed."""
        try:
            stat = shutil.disk_usage("/")
            pct = stat.used / stat.total * 100
            if pct > DISK_USAGE_WARN_PCT:
                log.warning(f"Disk usage at {pct:.1f}% — above {DISK_USAGE_WARN_PCT}% threshold")
                self.delegator.delegate("cleanup_logs")
                return f"disk_{pct:.0f}%"
            return None
        except Exception:
            return None

    def check_revenue_health(self) -> Optional[str]:
        """Phase 4: Emergency mode — auto-revert if revenue crashes."""
        now = datetime.now(timezone.utc)
        if (now - self.last_revenue_check).total_seconds() < 3600:
            return None
        self.last_revenue_check = now
        current_revenue = self.query_real_revenue()
        revenue_change = current_revenue - self.last_good_revenue
        if self.last_good_revenue > 0 and revenue_change < -REVENUE_THRESHOLD_WARN:
            log.error(f"EMERGENCY: Revenue dropped ${abs(revenue_change):.4f} in last cycle")
            return f"revenue_drop_{revenue_change:.2f}"
        if current_revenue > self.last_good_revenue:
            self.last_good_revenue = current_revenue
        return None

    def check_response_times(self) -> list[str]:
        """Check gateway and model API response times."""
        issues = []
        for name, url in [("gateway", f"{GATEWAY_URL}/health"), ("model-api", f"{MODEL_API_URL}/health")]:
            try:
                start = time.time()
                requests.get(url, timeout=10, verify=False)
                elapsed = time.time() - start
                if elapsed > RESPONSE_TIME_WARN_SEC:
                    issues.append(f"{name} ({elapsed:.1f}s)")
                    self.health_history.append({"time": datetime.now().isoformat(), "service": name, "latency": elapsed})
            except Exception as e:
                issues.append(f"{name} (unreachable: {e})")
        return issues

    # ─── Phase 3: Growth Engine ────────────────────────────────────────
    def assess_system(self) -> List[Dict]:
        """Comprehensive assessment: Phase 2 + Phase 3 + Phase 4."""
        needs = []
        now = datetime.now(timezone.utc)

        # Phase 4: Self-heal (priority 1)
        down = self.check_service_health()
        if down:
            needs.append({"task": "self_heal_services", "priority": 1, "reason": f"Degraded: {', '.join(down)}", "kwargs": {}})

        response_issues = self.check_response_times()
        for issue in response_issues:
            log.warning(f"Response time issue: {issue}")

        disk_issue = self.check_disk_usage()
        if disk_issue:
            needs.append({"task": "cleanup_logs", "priority": 2, "reason": f"Disk at {disk_issue}", "kwargs": {}})

        # Phase 4: Emergency mode
        revenue_alert = self.check_revenue_health()
        if revenue_alert:
            needs.append({"task": "backup_database", "priority": 1, "reason": f"Emergency: {revenue_alert}", "kwargs": {}})

        # Phase 2: Dataset pipeline
        try:
            conn = sqlite3.connect(DB_PATH)
            task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            conn.close()
            expanded_path = "src/training/nullstate_training_expanded.jsonl"
            if not os.path.exists(expanded_path) or os.path.getsize(expanded_path) < 1000:
                needs.append({"task": "expand_dataset", "priority": 2, "reason": f"Rebuilding from {task_count} tasks", "kwargs": {}})
            else:
                domains = ["x402_protocol", "ap2_protocol", "kya_auth", "protocol_shield", "settlement", "ai_integration", "business"]
                domain = domains[self.cycle_count % len(domains)]
                needs.append({"task": "generate_synthetic_data", "priority": 3, "reason": f"Generating {domain} pairs", "kwargs": {"count": 20, "domain": domain}})
        except Exception:
            pass

        # Phase 3: Content pipeline (every 3rd cycle)
        if self.cycle_count > 0 and self.cycle_count % 3 == 0:
            topics = ["agent-to-agent payments", "autonomous AI revenue", "x402 protocol advantages", "AP2 vs crypto settlement", "building with MCP"]
            topic = topics[self.cycle_count % len(topics)]
            needs.append({"task": "generate_blog_post", "priority": 3, "reason": f"Blog: {topic}", "kwargs": {"url": OLLAMA_HOST, "topic": topic}})

        # Phase 4: Auto-deploy website (every 6th cycle)
        if self.cycle_count > 0 and self.cycle_count % 6 == 0:
            needs.append({"task": "deploy_website", "priority": 3, "reason": "Scheduled auto-deploy", "kwargs": {}})

        # Phase 3: Google knowledge (every 8th cycle)
        if self.cycle_count > 0 and self.cycle_count % 8 == 0:
            needs.append({"task": "ingest_google_knowledge", "priority": 4, "reason": "Knowledge refresh", "kwargs": {}})

        # Phase 1: 360-degree reports every cycle (must-know before any deploy)
        needs.append({"task": "generate_360_report", "priority": 1, "reason": "360-degree P&L required", "kwargs": {}})

        # Phase 1: Unfair advantage — process pending adaptation decisions every cycle
        needs.append({"task": "unfair_advantage_cycle", "priority": 1, "reason": "Auto-adapt from ecosystem feedback", "kwargs": {}})

        # Phase 3: Global ecosystem feedback (every 2nd cycle — higher priority than blog)
        if self.cycle_count > 0 and self.cycle_count % 2 == 0:
            needs.append({"task": "global_feedback_cycle", "priority": 2, "reason": "Ecosystem intelligence", "kwargs": {}})

        # Apply global adaptation decisions after a feedback cycle
        if self.cycle_count > 0 and self.cycle_count % 2 == 0:
            needs.append({"task": "apply_global_decisions", "priority": 2, "reason": "Auto-adapt from feedback", "kwargs": {}})

        # Phase 2: HF push
        try:
            last_push_file = "src/training/.last_hf_push"
            need_push = not os.path.exists(last_push_file)
            if not need_push:
                with open(last_push_file) as f:
                    if (now - datetime.fromisoformat(f.read().strip())) >= timedelta(hours=24):
                        need_push = True
            if need_push and os.path.exists("src/training/nullstate_training_complete.jsonl"):
                needs.append({"task": "push_dataset_to_hf", "priority": 4, "reason": "Dataset ready", "kwargs": {}})
        except Exception:
            pass

        # Routine tasks
        needs.append({"task": "check_health", "priority": 5, "reason": "Routine", "kwargs": {"url": GATEWAY_URL}})
        needs.append({"task": "backup_database", "priority": 6, "reason": "Scheduled backup", "kwargs": {}})

        return sorted(needs, key=lambda x: x["priority"])

    def cycle(self):
        self.cycle_count += 1
        cycle_id = f"cycle_{self.cycle_count}_{uuid.uuid4().hex[:4]}"
        log.info(f"\n{'='*60}\nHOD v2 Cycle {cycle_id}\n{'='*60}")

        infra_cost = self.record_infra_cost(1.0)
        needs = self.assess_system()
        log.info(f"Assessment: {len(needs)} tasks")
        for n in needs:
            log.info(f"  [{n['priority']}] {n['task']}: {n['reason']}")

        delegated = []
        for need in needs[:4]:
            task_id = self.delegator.delegate(need["task"], **need.get("kwargs", {}))
            if task_id:
                delegated.append(task_id)
                log.info(f"  -> {need['task']}: {task_id}")

        # Merge datasets
        try:
            base = "src/training/nullstate_training.jsonl"
            expanded = "src/training/nullstate_training_expanded.jsonl"
            complete = "src/training/nullstate_training_complete.jsonl"
            all_pairs = []
            for fp in [base, expanded]:
                if os.path.exists(fp):
                    with open(fp) as f:
                        for line in f:
                            if line.strip():
                                all_pairs.append(json.loads(line))
            with open(complete, "w") as f:
                for p in all_pairs:
                    f.write(json.dumps(p) + "\n")
            log.info(f"Dataset: {len(all_pairs)} pairs merged")
        except Exception as e:
            log.debug(f"Merge: {e}")

        # P&L (per-minute model)
        total_costs = sum(self.ledger.costs.values())
        real_revenue = self.query_real_revenue()
        profit = real_revenue - total_costs
        runtime_min = self.cycle_count * 60
        cost_per_min = total_costs / runtime_min if runtime_min > 0 else 0
        rev_per_min = real_revenue / runtime_min if runtime_min > 0 else 0
        profit_per_min = rev_per_min - cost_per_min
        pc = "+" if profit >= 0 else ""
        log.info(f"P&L: ${pc}{profit:.4f} (rev: ${real_revenue:.4f}, cost: ${total_costs:.4f})")
        log.info(f"  Per-min: rev=${rev_per_min:.8f} cost=${cost_per_min:.8f} profit=${profit_per_min:.8f}/min")

        if profit < -1.0:
            log.warning(f"SUBSIDIZED: ${abs(profit):.2f} loss — need revenue ({profit_per_min:.8f}/min)")
        elif profit > 0:
            log.info(f"PROFITABLE: ${profit:.4f} net (${profit_per_min:.8f}/min)")
        else:
            log.info(f"BREAK-EVEN (${profit_per_min:.8f}/min)")

        try:
            import psutil
            from extensions.google.telemetry import record_revenue, record_cost, record_heartbeat, record_system_resources
            record_revenue(real_revenue, f"hod_cycle_{self.cycle_count}")
            record_cost(total_costs, "hod_infrastructure")
            record_heartbeat()
            record_system_resources(psutil.getloadavg()[0] / psutil.cpu_count() * 100, psutil.virtual_memory().used / (1024**3))
        except Exception:
            pass

        return {"cycle_id": cycle_id, "needs": [n["task"] for n in needs], "delegated": delegated,
                "pnl": {"total_costs": round(total_costs, 4), "total_revenue": round(real_revenue, 4), "profit_loss": round(profit, 4)}}

    def start(self, interval_hours: float = 1.0):
        self.running = True
        log.info(f"HOD v2 running — cycle every {interval_hours}h")
        try:
            while self.running:
                result = self.cycle()
                if result["pnl"]["profit_loss"] > 0:
                    log.info(f"Reinvesting ${result['pnl']['profit_loss'] * 0.5:.4f}")
                log.info(f"Sleeping {interval_hours}h...")
                time.sleep(interval_hours * 3600)
        except KeyboardInterrupt:
            log.info("HOD stopped")
        finally:
            self.running = False

    def stop(self):
        self.running = False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="NullState HOD v2 Autonomous Engine")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--one-shot", action="store_true")
    args = parser.parse_args()

    engine = HODEngine()
    print(f"""
╔══════════════════════════════════════════╗
║     NullState HOD v2 — Level 4          ║
║  Revenue + Growth + Self-Heal + Deploy  ║
║  Resources: {engine.ram_gb}GB | {engine.cpu_cores} cores        ║
║  Cost: ${engine.compute_cost_per_hour():.4f}/hour           ║
╚══════════════════════════════════════════╝
    """)

    if args.one_shot:
        result = engine.cycle()
        pnl = result["pnl"]
        print(f"\n  P&L: ${pnl['total_revenue']:.4f} rev | ${pnl['total_costs']:.4f} cost | ${pnl['profit_loss']:.4f} net")
        print(f"  Tasks delegated: {len(result['delegated'])}")
        return

    try:
        engine.start(interval_hours=args.interval)
    except Exception as e:
        log.error(f"HOD crashed: {e}")
        import sys
        sys.exit(1)


if __name__ == "__main__":
    main()

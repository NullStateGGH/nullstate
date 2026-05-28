"""NullState Unfair Advantage Adaptation Engine.
Closes the feedback loop: ecosystem signals → decisions → real changes → deploy.

Every piece of intelligence (web, social, competitor, market, P&L) triggers
autonomous adaptation. The system continuously evolves to widen its unfair advantage.

The cost/profit unit is USD/minute — every decision is measured against
per-minute profitability.
"""

import os
import json
import re
import time
import sqlite3
import logging
import subprocess
import shutil
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ADAPT] %(message)s")
log = logging.getLogger("nullstate-adaptation")

DB_PATH = os.environ.get("NULLSTATE_DB_PATH", "src/core/nullstate.db")
WEBSITE_DIR = "/home/Nullstate-linux-vm/nullstate-website"
BACKUP_DIR = "/home/Nullstate-linux-vm/backups"
SRC_DIR = "/home/Nullstate-linux-vm/src"
GEMINI_API_KEY = os.environ.get("NULLSTATE_GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS unfair_advantage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT, trigger_signal TEXT,
            decision TEXT, action_taken TEXT,
            files_changed TEXT, status TEXT,
            profit_before REAL, profit_after REAL,
            deploy_batch TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


def call_ai(prompt: str, max_tokens: int = 600) -> Optional[str]:
    try:
        if GEMINI_API_KEY:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
            resp = requests.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens}
            }, timeout=15)
            if resp.status_code == 200:
                cands = resp.json().get("candidates", [])
                if cands:
                    return cands[0]["content"]["parts"][0]["text"]
    except Exception:
        pass
    try:
        import requests
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": os.environ.get("NULLSTATE_MODEL", "nullstate"),
                  "prompt": prompt, "temperature": 0.2,
                  "max_tokens": max_tokens, "stream": False},
            timeout=120
        )
        if resp.status_code == 200:
            return resp.json().get("response")
    except Exception:
        pass
    return None


def get_pending_decisions(limit: int = 10) -> List[Dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, decision, reasoning, action_taken, status, timestamp FROM adaptation_decisions WHERE status = 'pending' ORDER BY id ASC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_applied(decision_id: int, action: str, files: list):
    conn = get_db()
    conn.execute(
        "UPDATE adaptation_decisions SET status = 'applied' WHERE id = ?",
        (decision_id,)
    )
    conn.execute(
        "INSERT INTO unfair_advantage_log (source, trigger_signal, decision, action_taken, files_changed, status) VALUES (?,?,?,?,?,?)",
        ("adaptation_engine", str(decision_id), action, "applied", json.dumps(files), "completed")
    )
    conn.commit()
    conn.close()


def mark_requires_review(decision_id: int, reason: str):
    conn = get_db()
    conn.execute(
        "UPDATE adaptation_decisions SET status = ? WHERE id = ?",
        (f"requires_review: {reason[:100]}", decision_id)
    )
    conn.commit()
    conn.close()


def backup_file(filepath: str) -> str:
    bak_dir = Path(BACKUP_DIR) / "adaptation"
    bak_dir.mkdir(parents=True, exist_ok=True)
    bak_path = bak_dir / f"{Path(filepath).name}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
    if os.path.exists(filepath):
        shutil.copy2(filepath, bak_path)
    return str(bak_path)


def apply_config_change(decision_id: int, decision_text: str, reasoning: str) -> bool:
    """Apply safe config changes based on decision patterns."""
    text = decision_text.lower()

    docusaurus_config = f"{WEBSITE_DIR}/docusaurus.config.ts"

    if "canonical" in text and "url" in text:
        _bak = backup_file(docusaurus_config)
        with open(docusaurus_config) as f:
            content = f.read()
        if "url:" in content and "greensol.me" not in content:
            content = re.sub(r'url:\s*["\'].*?["\']', 'url: \'https://greensol.me\'', content)
            content = re.sub(r'baseUrl:\s*["\'].*?["\']', 'baseUrl: \'/\'', content)
            with open(docusaurus_config, 'w') as f:
                f.write(content)
            log.info("Applied canonical URL fix")
            mark_applied(decision_id, "Fixed canonical URL in docusaurus.config.ts", [docusaurus_config])
            return True

    if "title" in text or "meta" in text or "description" in text:
        _bak = backup_file(docusaurus_config)
        with open(docusaurus_config) as f:
            content = f.read()
        if "title:" in content and "NullState" not in content:
            content = re.sub(r'title:\s*["\'].*?["\']', 'title: \'NullState — AI Agent Payment Layer\'', content)
            content = re.sub(r'tagline:\s*["\'].*?["\']', 'tagline: \'Open-source payment/settlement infrastructure for autonomous AI agents\'', content)
            with open(docusaurus_config, 'w') as f:
                f.write(content)
            log.info("Applied SEO title fix")
            mark_applied(decision_id, "Fixed meta titles", [docusaurus_config])
            return True

    if "footer" in text or "link" in text or "social" in text:
        log.info(f"Config change queued for review: {decision_text[:80]}")
        mark_requires_review(decision_id, "Footer/social changes need manual review")
        return False

    if "baseurl" in text or "base" in text:
        _bak = backup_file(docusaurus_config)
        with open(docusaurus_config) as f:
            content = f.read()
        content = re.sub(r'baseUrl:\s*["\'].*?["\']', 'baseUrl: \'/nullstate/\'', content)
        with open(docusaurus_config, 'w') as f:
            f.write(content)
        log.info("Applied baseUrl fix")
        mark_applied(decision_id, "Fixed baseUrl", [docusaurus_config])
        return True

    mark_requires_review(decision_id, f"Unrecognized config change pattern: {decision_text[:80]}")
    return False


def apply_content_create(decision_id: int, decision_text: str, reasoning: str) -> bool:
    """Create blog posts or website content based on decisions."""
    text = decision_text.lower()
    topic = text.replace("create blog post about", "").replace("write post about", "")
    topic = topic.replace("create content about", "").replace("publish article about", "").strip()
    topic = re.sub(r'^["\']|["\']$', '', topic)

    if not topic or len(topic) < 5:
        topic = reasoning[:80] if len(reasoning) > 80 else "AI agent ecosystem"

    prompt = f"""Write a 400-word technical blog post for NullState (open-source AI agent payment infrastructure).
Topic: {topic}
Target audience: AI developers building autonomous agents.
Include: technical insights, code examples or architecture notes, and a conclusion about agent payments.
Use markdown. Title as H1."""

    content = call_ai(prompt, max_tokens=800)
    if not content:
        log.warning(f"AI failed to generate content for: {topic}")
        return False

    blog_dir = Path(f"{WEBSITE_DIR}/blog")
    blog_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = re.sub(r'[^a-z0-9]+', '-', topic.lower())[:40]
    filepath = blog_dir / f"{date_str}-adapt-{slug}.md"
    header = f"---\nslug: adapt-{slug}\ntitle: {topic.title()}\nauthors: [hod]\ntags: [adaptation, ai, automatic]\n---\n\n"
    filepath.write_text(header + content)
    log.info(f"Blog post created: {filepath}")
    mark_applied(decision_id, f"Blog post: {topic}", [str(filepath)])
    return True


def apply_deploy_action(decision_id: int, decision_text: str) -> bool:
    """Trigger website rebuild and deploy."""
    log.info(f"Deploy triggered by adaptation decision: {decision_text[:80]}")
    try:
        result = subprocess.run(
            ["npx", "docusaurus", "build"],
            cwd=WEBSITE_DIR, capture_output=True, text=True, timeout=180
        )
        if result.returncode == 0:
            mark_applied(decision_id, "Website rebuilt for deploy", [f"{WEBSITE_DIR}/build"])
            return True
        else:
            log.warning(f"Build failed: {result.stderr[-200:]}")
            mark_requires_review(decision_id, "Website build failed")
            return False
    except Exception as e:
        log.warning(f"Deploy failed: {e}")
        mark_requires_review(decision_id, f"Deploy error: {e}")
        return False


def apply_research_action(decision_id: int, decision_text: str, reasoning: str) -> bool:
    """Generate a research report from the decision."""
    prompt = f"""Write a brief research analysis for NullState (AI agent payment infrastructure).
Topic: {decision_text}
Context: {reasoning}
Provide actionable insights and recommendations. Max 300 words."""
    report = call_ai(prompt, max_tokens=500)
    if report:
        reports_dir = Path(f"{WEBSITE_DIR}/static/research")
        reports_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        slug = re.sub(r'[^a-z0-9]+', '-', decision_text.lower())[:30]
        filepath = reports_dir / f"{date_str}-{slug}.md"
        filepath.write_text(f"# Research: {decision_text}\n\n{report}")
        log.info(f"Research report saved: {filepath}")
        mark_applied(decision_id, f"Research report: {decision_text[:60]}", [str(filepath)])
        return True
    return False


def execute_adaptation_cycle() -> Dict:
    """Run one complete adaptation cycle — process all pending decisions."""
    log.info(f"\n{'='*60}")
    log.info("Adaptation Cycle — checking for pending decisions")
    log.info(f"{'='*60}")

    pending = get_pending_decisions(20)
    if not pending:
        log.info("No pending decisions to apply")
        return {"processed": 0, "applied": 0, "requires_review": 0, "actions": []}

    applied_count = 0
    review_count = 0
    actions = []

    for dec in pending:
        decision_text = dec["decision"]
        reasoning = dec.get("reasoning", "")
        action_type = dec.get("action_taken", "research")
        decision_id = dec["id"]

        log.info(f"  [{decision_id}] {action_type}: {decision_text[:80]}...")

        try:
            if action_type == "config_change":
                ok = apply_config_change(decision_id, decision_text, reasoning)
            elif action_type == "content_create":
                ok = apply_content_create(decision_id, decision_text, reasoning)
            elif action_type == "deploy":
                ok = apply_deploy_action(decision_id, decision_text)
            elif action_type == "research" or action_type == "outreach":
                ok = apply_research_action(decision_id, decision_text, reasoning)
            elif action_type == "code_change":
                # Code changes need review — too risky for autonomous
                mark_requires_review(decision_id, "Code changes require manual review")
                ok = False
                review_count += 1
            else:
                mark_requires_review(decision_id, f"Unknown action type: {action_type}")
                ok = False
                review_count += 1

            if ok:
                applied_count += 1
                actions.append(f"Applied: {decision_text[:60]}")
            else:
                review_count += 1
        except Exception as e:
            log.warning(f"  Error applying decision {decision_id}: {e}")
            mark_requires_review(decision_id, f"Error: {e}")
            review_count += 1

    log.info(f"Adaptation cycle: {applied_count} applied, {review_count} need review")
    return {
        "total_pending": len(pending),
        "applied": applied_count,
        "requires_review": review_count,
        "actions": actions,
    }


def get_unfair_advantage_summary() -> str:
    """Generate a summary of the unfair advantage loop performance."""
    conn = get_db()
    total_decisions = conn.execute("SELECT COUNT(*) FROM adaptation_decisions").fetchone()[0]
    applied = conn.execute("SELECT COUNT(*) FROM adaptation_decisions WHERE status = 'applied'").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM adaptation_decisions WHERE status = 'pending'").fetchone()[0]
    review = conn.execute("SELECT COUNT(*) FROM adaptation_decisions WHERE status LIKE 'requires_review%'").fetchone()[0]
    total_signals = conn.execute("SELECT COUNT(*) FROM ecosystem_signals").fetchone()[0]
    sources = conn.execute("SELECT COUNT(DISTINCT source) FROM ecosystem_signals").fetchone()[0]

    last_report = conn.execute(
        "SELECT total_cost, total_revenue, total_profit, profit_per_min, report_id FROM unified_reports ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    lines = ["# NullState Unfair Advantage Summary"]
    lines.append(f"*Generated: {datetime.now(timezone.utc).isoformat()}*\n")

    lines.append("## Feedback Loop")
    lines.append(f"- Ecosystem signals collected: {total_signals} from {sources} sources")
    lines.append(f"- Adaptation decisions generated: {total_decisions}")
    lines.append(f"- Decisions applied: {applied}")
    lines.append(f"- Decisions pending: {pending}")
    lines.append(f"- Decisions needing review: {review}")
    lines.append(f"- Auto-apply rate: {applied/max(total_decisions,1)*100:.0f}%\n")

    lines.append("## Per-Minute P&L")
    if last_report:
        lines.append(f"- Latest report: {last_report['report_id']}")
        lines.append(f"- Total cost: ${last_report['total_cost']:.6f}")
        lines.append(f"- Total revenue: ${last_report['total_revenue']:.6f}")
        lines.append(f"- Total profit: ${last_report['total_profit']:.6f}")
        lines.append(f"- Profit per minute: ${last_report['profit_per_min']:.8f}/min")
    else:
        lines.append("- No reports yet\n")

    lines.append("## Competitive Moat")
    lines.append("- Global web intelligence scanning 6+ sources")
    lines.append("- 11 departments monitored per-minute")
    lines.append("- Autonomous adaptation from ecosystem signals")
    lines.append("- Continuous self-improvement via per-minute P&L feedback")

    report = "\n".join(lines)
    report_path = Path(f"{WEBSITE_DIR}/static/unfair_advantage.md")
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report)
        log.info("Unfair advantage report saved")
    except Exception:
        pass
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="NullState Unfair Advantage Adaptation Engine")
    parser.add_argument("--cycle", action="store_true", help="Process pending adaptation decisions")
    parser.add_argument("--summary", action="store_true", help="Show unfair advantage summary")
    parser.add_argument("--continuous", type=float, default=0, help="Run continuous cycle every N minutes")
    args = parser.parse_args()

    if args.summary:
        print(get_unfair_advantage_summary())
        return

    if args.continuous:
        log.info(f"Continuous adaptation: every {args.continuous} min")
        while True:
            execute_adaptation_cycle()
            get_unfair_advantage_summary()
            time.sleep(args.continuous * 60)
        return

    result = execute_adaptation_cycle()
    get_unfair_advantage_summary()
    print(f"\nAdaptation cycle: {result.get('applied',0)} applied, {result.get('requires_review',0)} need review")
    for a in result.get("actions", []):
        print(f"  {a}")


if __name__ == "__main__":
    main()

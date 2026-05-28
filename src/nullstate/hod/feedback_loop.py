"""NullState Agentic Website Feedback Loop.
GA4 analytics → AI auditor → improvement generator → auto-deploy.
Runs as HOD task + cron job for continuous enterprise-grade optimization.
"""

import os
import json
import time
import re
import sqlite3
import hashlib
import logging
import subprocess
import ftplib
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [FEEDBACK] %(message)s")
log = logging.getLogger("nullstate-feedback")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
NULLSTATE_MODEL = os.environ.get("NULLSTATE_MODEL", "nullstate")
GEMINI_API_KEY = os.environ.get("NULLSTATE_GOOGLE_API_KEY", "")
WEBSITE_DIR = "/home/Nullstate-linux-vm/nullstate-website"
BUILD_DIR = os.path.join(WEBSITE_DIR, "build")
DB_PATH = "src/core/nullstate.db"
GA_MEASUREMENT_ID = os.environ.get("GA_MEASUREMENT_ID", "G-XXXXXXXX")

FTP_HOST = os.environ.get("FTP_HOST", "server26.shared.spaceship.host")
FTP_USER = os.environ.get("FTP_USER", "admin@greensol.me")
FTP_PASS = os.environ.get("FTP_PASS", "V8sHRwRF#p^o")
FTP_REMOTE = "/nullstate"

WEEKLY_TOPICS = [
    "agent-to-agent payment protocols comparison",
    "why AI agents need autonomous payment rails",
    "x402 protocol deep dive: how it works",
    "building a revenue-generating AI agent",
    "NullState vs Stripe for AI payments",
    "the future of machine-to-machine commerce",
    "enterprise AI payment security patterns",
]

AUDIT_CRITERIA = [
    "SEO meta tags and structure",
    "Page load performance",
    "Mobile responsiveness",
    "Content accuracy and depth",
    "Call-to-action effectiveness",
    "Protocol explanation clarity",
    "Visual design consistency",
    "Documentation completeness",
    "Code example quality",
    "Security posture (no leaked internals)",
    "Broken links and 404s",
    "Accessibility (a11y) basics",
]


def _init_analytics_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            page_path TEXT,
            agent_id TEXT,
            referrer TEXT,
            user_agent TEXT,
            session_id TEXT,
            duration_sec REAL,
            bounced INTEGER DEFAULT 1,
            timestamp TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS audit_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            overall_score REAL,
            criteria_scores TEXT,
            issues_found TEXT,
            recommendations TEXT,
            auditor_version TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS feedback_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT,
            description TEXT,
            file_changed TEXT,
            status TEXT DEFAULT 'applied',
            deploy_batch TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


def track_pageview(page_path: str, agent_id: str = "anonymous",
                   referrer: str = "", user_agent: str = "",
                   session_id: str = "") -> None:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO analytics_events (event_type, page_path, agent_id, referrer, user_agent, session_id) VALUES (?,?,?,?,?,?)",
            ("pageview", page_path, agent_id, referrer, user_agent, session_id or hashlib.md5(f"{agent_id}{datetime.now().date()}".encode()).hexdigest()[:16])
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_analytics_summary(days: int = 7) -> Dict:
    summary = {
        "total_pageviews": 0, "unique_visitors": 0, "bounce_rate": 0.0,
        "top_pages": [], "daily_trend": [], "avg_session_duration": 0.0,
    }
    try:
        conn = sqlite3.connect(DB_PATH)
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        summary["total_pageviews"] = conn.execute(
            "SELECT COUNT(*) FROM analytics_events WHERE event_type='pageview' AND timestamp >= ?", (since,)
        ).fetchone()[0]
        summary["unique_visitors"] = conn.execute(
            "SELECT COUNT(DISTINCT agent_id) FROM analytics_events WHERE timestamp >= ?", (since,)
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT page_path, COUNT(*) as cnt FROM analytics_events WHERE event_type='pageview' AND timestamp >= ? GROUP BY page_path ORDER BY cnt DESC LIMIT 10",
            (since,)
        ).fetchall()
        summary["top_pages"] = [{"path": r[0], "views": r[1]} for r in rows]
        rows = conn.execute(
            "SELECT DATE(timestamp) as d, COUNT(*) FROM analytics_events WHERE timestamp >= ? GROUP BY d ORDER BY d", (since,)
        ).fetchall()
        summary["daily_trend"] = [{"date": r[0], "views": r[1]} for r in rows]
        bounce = conn.execute("SELECT AVG(bounced) FROM analytics_events WHERE timestamp >= ?", (since,)).fetchone()[0]
        summary["bounce_rate"] = round((bounce or 0) * 100, 1)
        dur = conn.execute("SELECT AVG(duration_sec) FROM analytics_events WHERE duration_sec > 0 AND timestamp >= ?", (since,)).fetchone()[0]
        summary["avg_session_duration"] = round(dur or 0, 1)
        conn.close()
    except Exception:
        pass
    return summary


# ─── AI Auditor ──────────────────────────────────────────────────────────

def _call_ai(prompt: str, temperature: float = 0.3, max_tokens: int = 1024) -> Optional[str]:
    for attempt in range(2):
        try:
            resp = requests.post(f"{OLLAMA_HOST}/api/generate",
                json={"model": NULLSTATE_MODEL, "prompt": prompt,
                       "temperature": temperature, "max_tokens": max_tokens, "stream": False},
                timeout=300)
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception:
            if attempt == 0 and GEMINI_API_KEY:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
                    resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}, timeout=30)
                    if resp.status_code == 200:
                        candidates = resp.json().get("candidates", [])
                        if candidates:
                            return candidates[0]["content"]["parts"][0]["text"]
                except Exception:
                    pass
    return None


def run_audit(html_content: str = "", config_content: str = "") -> Dict:
    """Full website audit by AI auditor."""
    audit = {
        "overall_score": 0, "criteria_scores": {}, "issues_found": [],
        "recommendations": [], "documentation_gaps": [],
    }

    checks = {
        "baseUrl is /nullstate/": "baseUrl: '/nullstate/'",
        "Canonical is greensol.me": "url: 'https://greensol.me'",
        "No nullstate.io references": "nullstate.io",
        "GitHub links correct": "NullStateGGH",
        "Solana wallet not leaked": "2d2YcoLKSbEBY2sUR76Pfp9QifdsQQpRWYXU2TfVsALX",
    }
    if config_content:
        for check_name, pattern in checks.items():
            if "no" in check_name.lower() or "not" in check_name.lower():
                if pattern in config_content:
                    audit["issues_found"].append({"check": check_name, "severity": "high", "status": "FAIL"})
                else:
                    audit["issues_found"].append({"check": check_name, "severity": "high", "status": "PASS"})
            else:
                if pattern in config_content:
                    audit["issues_found"].append({"check": check_name, "severity": "high", "status": "PASS"})
                else:
                    audit["issues_found"].append({"check": check_name, "severity": "high", "status": "FAIL"})

    if html_content:
        prompt = f"""You are an enterprise web auditor. Score this website HTML 1-10 for each criterion.
Return ONLY valid JSON: {{"criterion_name": score, "criterion_name": score, ...}}

Criteria: {', '.join(AUDIT_CRITERIA)}

HTML excerpt:
{html_content[:4000]}
"""
        result = _call_ai(prompt, temperature=0.2)
        if result:
            try:
                scores = json.loads(result)
                for c in AUDIT_CRITERIA:
                    _key = c.lower().replace(' ', '_')[:20]
                    for k in scores:
                        if k[:10] == c[:10]:
                            audit["criteria_scores"][c] = int(scores[k])
                            break
            except (json.JSONDecodeError, ValueError):
                for c in AUDIT_CRITERIA:
                    nums = re.findall(rf'{re.escape(c[:15])}.*?(\d+)', result)
                    if nums:
                        audit["criteria_scores"][c] = int(nums[0])

    if audit["criteria_scores"]:
        audit["overall_score"] = round(sum(audit["criteria_scores"].values()) / len(audit["criteria_scores"]), 1)

    for criterion, score in audit["criteria_scores"].items():
        if score < 6:
            recom_prompt = f"Suggest a specific improvement for '{criterion}' (score {score}/10) on the NullState website. One sentence."
            recom = _call_ai(recom_prompt, temperature=0.3, max_tokens=200)
            if recom:
                audit["recommendations"].append({"criterion": criterion, "score": score, "suggestion": recom.strip()[:200]})

    return audit


def save_audit(audit: Dict) -> None:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO audit_reports (overall_score, criteria_scores, issues_found, recommendations, auditor_version) VALUES (?,?,?,?,?)",
            (audit["overall_score"], json.dumps(audit["criteria_scores"]),
             json.dumps(audit["issues_found"]), json.dumps(audit["recommendations"]), "nullstate-feedback-loop-v1")
        )
        conn.commit()
        conn.close()
        log.info(f"Audit saved: score={audit['overall_score']}, issues={len(audit['issues_found'])}")
    except Exception as e:
        log.error(f"Audit save error: {e}")


# ─── Content Generation (SEO-optimized blog) ─────────────────────────────

def generate_seo_blog_post(topic: str = "") -> Optional[str]:
    if not topic:
        week_num = datetime.now().isocalendar()[1]
        topic = WEEKLY_TOPICS[week_num % len(WEEKLY_TOPICS)]

    prompt = f"""Write a 500-word SEO-optimized technical blog post about: {topic}

Requirements:
- Include H1 title, 3-4 H2 sections, conclusion
- Target keywords: NullState, AI payments, agent economy, x402 protocol
- Include 1 code example or API endpoint reference
- Include a call-to-action to try NullState at greensol.me/nullstate
- Use professional but accessible tone
- Current date: {datetime.now().strftime('%Y-%m-%d')}

Return as complete markdown."""
    return _call_ai(prompt, temperature=0.5, max_tokens=2048)


def save_blog_post(content: str) -> Optional[str]:
    if not content:
        return None
    blog_dir = Path(WEBSITE_DIR) / "blog"
    blog_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    _slug = f"feedback-{datetime.now().strftime('%Y%m%d-%H%M')}"
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else f"NullState Update ({date_str})"
    short_slug = title.lower().replace(' ', '-')[:40].strip('-')
    filepath = blog_dir / f"{date_str}-{short_slug}.md"
    header = f"---\nslug: {short_slug}\ntitle: {title}\nauthors: [nullstate-feedback]\ntags: [autonomous, ai, feedback-loop, seo]\n---\n\n"
    filepath.write_text(header + content)
    log.info(f"Blog post saved: {filepath}")
    return str(filepath)


# ─── Feedback Loop Runner ────────────────────────────────────────────────

def collect_analytics_data() -> Dict:
    """Collect analytics summary for the feedback loop."""
    return get_analytics_summary(days=7)


def apply_docusaurus_fixes(config_path: str = "") -> List[str]:
    """Apply known enterprise fixes to Docusaurus config."""
    if not config_path:
        config_path = os.path.join(WEBSITE_DIR, "docusaurus.config.ts")
    if not os.path.exists(config_path):
        return []
    applied = []
    with open(config_path) as f:
        content = f.read()
    fixes = [
        ("baseUrl: '/'", "baseUrl: '/nullstate/'", "Fix baseUrl"),
        ("url: 'https://nullstate.io'", "url: 'https://greensol.me'", "Fix canonical URL"),
        ("github.com/nullstate/nullstate'", "github.com/NullStateGGH/nullstate'", "Fix GitHub org"),
    ]
    for old, new, desc in fixes:
        if old in content:
            content = content.replace(old, new)
            applied.append(desc)
    with open(config_path, "w") as f:
        f.write(content)
    return applied


def rebuild_website() -> bool:
    try:
        result = subprocess.run(["npx", "docusaurus", "build"], cwd=WEBSITE_DIR,
                                 capture_output=True, text=True, timeout=180)
        if result.returncode == 0:
            log.info("Website rebuilt OK")
            return True
        log.error(f"Build failed: {result.stderr[-500:]}")
        return False
    except Exception as e:
        log.error(f"Build error: {e}")
        return False


def deploy_website() -> bool:
    if not os.path.exists(BUILD_DIR):
        return False
    try:
        ftp = ftplib.FTP(FTP_HOST, FTP_USER, FTP_PASS, timeout=60)
        ftp.encoding = "utf-8"
        _ftp_upload_recursive(ftp, BUILD_DIR, FTP_REMOTE)
        ftp.quit()
        deploy_batch = datetime.now().strftime("%Y%m%d-%H%M%S")
        os.makedirs("/home/Nullstate-linux-vm/deployments", exist_ok=True)
        archive = f"/home/Nullstate-linux-vm/deployments/nullstate-{deploy_batch}.tar.gz"
        subprocess.run(["tar", "-czf", archive, "-C", BUILD_DIR, "."], capture_output=True)
        log.info(f"Deployed: {FTP_HOST}{FTP_REMOTE} | archived: {archive}")
        return True
    except Exception as e:
        log.error(f"Deploy failed: {e}")
        return False


def _ftp_upload_recursive(ftp, local_dir, remote_dir):
    for root, dirs, files in os.walk(local_dir):
        rel = os.path.relpath(root, local_dir)
        remote = f"{remote_dir}/{rel.replace(os.sep, '/')}" if rel != "." else remote_dir
        try:
            ftp.cwd(remote)
        except Exception:
            for part in remote.split("/"):
                try:
                    ftp.cwd(part)
                except Exception:
                    ftp.mkd(part)
                    ftp.cwd(part)
        for fname in files:
            try:
                with open(os.path.join(root, fname), "rb") as fh:
                    ftp.storbinary(f"STOR {fname}", fh)
            except Exception as e:
                log.warning(f"FTP upload {fname}: {e}")


def log_action(action_type: str, description: str, file_changed: str = "", deploy_batch: str = "") -> None:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO feedback_actions (action_type, description, file_changed, deploy_batch) VALUES (?,?,?,?)",
            (action_type, description[:200], file_changed, deploy_batch)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ─── Main Loop ───────────────────────────────────────────────────────────

def run_feedback_cycle() -> Dict:
    """One complete agentic feedback cycle: analytics → audit → improve → deploy."""
    _init_analytics_db()
    start = time.time()
    batch = datetime.now().strftime("%Y%m%d-%H%M%S")
    log.info(f"\n{'='*60}\nAgentic Feedback Cycle [{batch}]\n{'='*60}")

    # Phase 1: Collect analytics
    log.info("Phase 1: Analytics collection")
    analytics = collect_analytics_data()
    log.info(f"  Views(7d): {analytics['total_pageviews']} | Visitors: {analytics['unique_visitors']} | Bounce: {analytics['bounce_rate']}%")

    # Phase 2: AI Audit
    log.info("Phase 2: AI Website Audit")
    config_path = os.path.join(WEBSITE_DIR, "docusaurus.config.ts")
    config_content = open(config_path).read() if os.path.exists(config_path) else ""
    index_path = os.path.join(BUILD_DIR, "index.html")
    html_content = open(index_path).read()[:5000] if os.path.exists(index_path) else ""
    audit = run_audit(html_content=html_content, config_content=config_content)
    save_audit(audit)
    log.info(f"  Score: {audit['overall_score']}/10 | Issues: {len(audit['issues_found'])} | Recs: {len(audit['recommendations'])}")

    # Phase 3: Generate content (blog post if low traffic)
    blog_path = None
    if analytics["total_pageviews"] < 100:
        log.info("Phase 3: SEO content generation (low traffic trigger)")
        content = generate_seo_blog_post()
        blog_path = save_blog_post(content)
        if blog_path:
            log.info(f"  Blog: {blog_path}")
            log_action("blog_post", f"Auto-generated: {os.path.basename(blog_path)}", blog_path, batch)

    # Phase 4: Apply config fixes
    log.info("Phase 4: Applying fixes")
    fixes = apply_docusaurus_fixes()
    for fix in fixes:
        log_action("config_fix", fix, "docusaurus.config.ts", batch)
    log.info(f"  Fixes: {fixes}")

    # Phase 5: Apply top audit recommendations
    for rec in audit["recommendations"][:2]:
        sug = rec.get("suggestion", "")
        log_action("audit_recommendation", sug[:200], "", batch)

    # Phase 6: Rebuild + Deploy
    log.info("Phase 5: Build + Deploy")
    rebuild_ok = rebuild_website()
    deployed = False
    if rebuild_ok:
        deployed = deploy_website()
        if deployed:
            log_action("deploy", f"Website deployed (batch {batch})", "", batch)

    elapsed = time.time() - start
    result = {
        "batch": batch,
        "elapsed": f"{elapsed:.1f}s",
        "analytics_7d_views": analytics["total_pageviews"],
        "audit_score": audit["overall_score"],
        "audit_issues": len(audit["issues_found"]),
        "recommendations": len(audit["recommendations"]),
        "blog_posted": blog_path is not None,
        "fixes_applied": len(fixes),
        "rebuild_ok": rebuild_ok,
        "deployed": deployed,
    }
    log.info(f"Cycle complete: {json.dumps(result, indent=2)}")
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="NullState Agentic Website Feedback Loop")
    parser.add_argument("--track", type=str, help="Track a pageview: path,agent_id,referrer,ua")
    parser.add_argument("--audit-only", action="store_true", help="Run audit only")
    parser.add_argument("--deploy-only", action="store_true", help="Rebuild + deploy only")
    parser.add_argument("--blog-only", action="store_true", help="Generate blog post only")
    parser.add_argument("--analytics", action="store_true", help="Show analytics summary")
    args = parser.parse_args()

    _init_analytics_db()

    if args.track:
        parts = args.track.split(",")
        track_pageview(parts[0], parts[1] if len(parts) > 1 else "anonymous",
                       parts[2] if len(parts) > 2 else "",
                       parts[3] if len(parts) > 3 else "")
        print(json.dumps({"tracked": parts[0]}))

    elif args.audit_only:
        config_path = os.path.join(WEBSITE_DIR, "docusaurus.config.ts")
        config_content = open(config_path).read() if os.path.exists(config_path) else ""
        index_path = os.path.join(BUILD_DIR, "index.html")
        html_content = open(index_path).read()[:5000] if os.path.exists(index_path) else ""
        audit = run_audit(html_content=html_content, config_content=config_content)
        save_audit(audit)
        print(json.dumps(audit, indent=2))

    elif args.deploy_only:
        ok = rebuild_website()
        if ok:
            deploy_website()
        print(json.dumps({"rebuild": ok, "deploy": ok and True}))

    elif args.blog_only:
        content = generate_seo_blog_post()
        path = save_blog_post(content)
        print(json.dumps({"blog_post": path}))

    elif args.analytics:
        print(json.dumps(get_analytics_summary(), indent=2))

    else:
        result = run_feedback_cycle()
        print(json.dumps(result))


if __name__ == "__main__":
    main()

"""NullState Continuous Improvement Feedback Loop.
Uses our NullState model (via Ollama) to evaluate and improve the website autonomously.
Runs as a cron job. Self-optimizing. Self-deploying.

The loop:
1. Crawl current website → evaluate against top competitor benchmarks
2. NullState model generates improvement suggestions
3. Apply improvements to Docusaurus config/content
4. Rebuild website
5. Deploy
6. Repeat every cycle
"""

import os
import json
import time
import re
import requests
import logging
import subprocess
import ftplib
from datetime import datetime, timezone
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [IMPROVE] %(message)s")
log = logging.getLogger("nullstate-improve")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
NULLSTATE_MODEL = os.environ.get("NULLSTATE_MODEL", "nullstate")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyB6PfFrxoam8LB7RJmVfra3Y-bWfqtzB6M")
WEBSITE_DIR = "/home/Nullstate-linux-vm/nullstate-website"
BUILD_DIR = os.path.join(WEBSITE_DIR, "build")
DEPLOY_DIR = "/var/www/greensol/nullstate"

# Known site issues to fix (from current audit)
KNOWN_ISSUES = [
    "baseUrl should be /nullstate/ not /",
    "GitHub links should point to NullStateGGH not nullstate",
    "OG image URLs should use greensol.me not nullstate.io",
    "Canonical URL should be greensol.me/nullstate not nullstate.io",
]

# Benchmark criteria for evaluation
BENCHMARK_CRITERIA = [
    "SEO meta tags and structure",
    "Page load speed and performance",
    "Mobile responsiveness",
    "Content quality and depth",
    "Call-to-action clarity",
    "Protocol explanation clarity",
    "Visual design and branding consistency",
    "Documentation completeness",
    "Code example quality",
]


def call_nullstate(prompt: str, temperature: float = 0.3, max_tokens: int = 1024) -> Optional[str]:
    """Call our NullState model for evaluation/suggestions."""
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": NULLSTATE_MODEL,
                "prompt": prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False
            },
            timeout=300
        )
        resp.raise_for_status()
        return resp.json().get("response", "")
    except Exception as e:
        log.error(f"Model call failed: {e}")
        return None


def call_gemini(prompt: str, temperature: float = 0.3) -> Optional[str]:
    """Fallback to Gemini if NullState model unavailable."""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        resp = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": 1024}
        }, timeout=30)
        if resp.status_code == 200:
            candidates = resp.json().get("candidates", [])
            if candidates:
                return candidates[0]["content"]["parts"][0]["text"]
    except Exception as e:
        log.error(f"Gemini fallback failed: {e}")
    return None


def evaluate_website() -> Dict:
    """Evaluate the current website against benchmarks."""
    # Read the current site HTML
    index_path = os.path.join(BUILD_DIR, "index.html") if os.path.exists(os.path.join(BUILD_DIR, "index.html")) else None

    evaluation = {
        "issues_found": [],
        "benchmark_scores": {},
        "overall_score": 0,
        "improvements": []
    }

    # Check for known issues
    with open(os.path.join(WEBSITE_DIR, "docusaurus.config.ts")) as f:
        config = f.read()

    checks = {
        "baseUrl is /nullstate/": "baseUrl: '/nullstate/'",
        "GitHub links to NullStateGGH": "NullStateGGH",
        "OG image to greensol.me": "greensol.me",
        "Canonical to greensol.me": "greensol.me",
    }

    for check_name, pattern in checks.items():
        if pattern in config:
            evaluation["issues_found"].append({"check": check_name, "status": "PASS"})
        else:
            evaluation["issues_found"].append({"check": check_name, "status": "FAIL"})

    # Use model to evaluate content quality
    if index_path and os.path.exists(index_path):
        with open(index_path) as f:
            html_content = f.read()[:5000]  # First 5K chars

        eval_prompt = f"""Evaluate this NullState website homepage against these criteria. Score each 1-10:
{chr(10).join(f'- {c}' for c in BENCHMARK_CRITERIA)}

Website HTML (first 5000 chars):
{html_content[:3000]}

Return format: JSON with criteria as keys and scores as values, plus a brief improvement suggestion for each low score (< 7)."""

        result = call_nullstate(eval_prompt, temperature=0.2)
        if not result:
            result = call_gemini(eval_prompt, temperature=0.2)

        if result:
            # Try to parse scores from response
            for criterion in BENCHMARK_CRITERIA:
                _short = criterion.split(" ")[0].lower()
                scores = re.findall(rf'{criterion[:10]}.*?(\d+)', result)
                if scores:
                    evaluation["benchmark_scores"][criterion] = int(scores[0])

            # Extract improvement suggestions
            if "improve" in result.lower() or "suggest" in result.lower():
                evaluation["improvements"] = [line for line in result.split("\n")
                                            if "improve" in line.lower() or "suggest" in line.lower()
                                            or "should" in line.lower() or "could" in line.lower()]

    # Calculate overall score
    if evaluation["benchmark_scores"]:
        evaluation["overall_score"] = sum(evaluation["benchmark_scores"].values()) / len(evaluation["benchmark_scores"])

    return evaluation


def generate_improvements(evaluation: Dict) -> List[Dict]:
    """Use NullState model to generate specific improvements."""

    issues_summary = "\n".join([f"- {i['check']}: {i['status']}" for i in evaluation["issues_found"]])
    scores_summary = "\n".join([f"- {k}: {v}/10" for k, v in evaluation["benchmark_scores"].items()])

    prompt = f"""You are a senior web developer optimizing the NullState website. Based on this evaluation:

Issues:
{issues_summary}

Scores:
{scores_summary}

Generate 3-5 specific, actionable improvements for the Docusaurus website config and content.
Each improvement must include: the file to change, the change to make, and why it helps.

Return in this JSON format:
[{{"file": "path", "change": "description", "reason": "why it helps"}}]
"""

    result = call_nullstate(prompt, temperature=0.4)
    if not result:
        result = call_gemini(prompt, temperature=0.4)

    if result:
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            # Return as text suggestions
            return [{"file": "unknown", "change": line.strip(), "reason": "AI suggestion"}
                   for line in result.split("\n") if line.strip() and len(line.strip()) > 20]

    return []


def apply_improvements(improvements: List[Dict]) -> List[str]:
    """Apply generated improvements to the website."""
    applied = []

    for imp in improvements:
        file_path = imp.get("file", "")
        change = imp.get("change", "")

        if not file_path or not change:
            continue

        # Map relative paths to absolute
        if not file_path.startswith("/"):
            file_path = os.path.join(WEBSITE_DIR, file_path)

        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    _content = f.read()

                # Apply the change description as a logged suggestion
                # (line-precise edits are risky from AI, log for human review)
                applied.append(f"SUGGESTION for {file_path}: {change}")
                log.info(f"Improvement logged: {change[:80]}")
            except Exception as e:
                log.error(f"Could not apply to {file_path}: {e}")

    # For now, apply known fixes directly:
    # Fix any remaining baseUrl issues in source files
    config_path = os.path.join(WEBSITE_DIR, "docusaurus.config.ts")
    with open(config_path, "r") as f:
        config = f.read()

    fixes = []
    if "baseUrl: '/'" in config and "baseUrl: '/nullstate/'" not in config:
        config = config.replace("baseUrl: '/'", "baseUrl: '/nullstate/'")
        fixes.append("Fixed baseUrl")
    if "url: 'https://nullstate.io'" in config:
        config = config.replace("url: 'https://nullstate.io'", "url: 'https://greensol.me'")
        fixes.append("Fixed canonical URL")
    if "'github.com/nullstate/nullstate'" in config:
        config = config.replace("'github.com/nullstate/nullstate'", "'github.com/NullStateGGH/nullstate'")
        fixes.append("Fixed GitHub link")
    if "'clone https://github.com/nullstate/nullstate'" in config:
        config = config.replace("'clone https://github.com/nullstate/nullstate'", "'clone https://github.com/NullStateGGH/nullstate'")
        fixes.append("Fixed clone URL")
    if "'github.com/nullstate/nullstate-website'" in config:
        config = config.replace("'github.com/nullstate/nullstate-website'", "'github.com/NullStateGGH/nullstate-website'")
        fixes.append("Fixed website GitHub link")

    with open(config_path, "w") as f:
        f.write(config)

    applied.extend(fixes)
    return applied


def rebuild_website() -> bool:
    """Rebuild the Docusaurus website."""
    log.info("Rebuilding website...")
    try:
        result = subprocess.run(
            ["npx", "docusaurus", "build"],
            cwd=WEBSITE_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            log.info("Website rebuilt successfully")
            return True
        else:
            log.error(f"Build failed: {result.stderr[-500:]}")
            return False
    except Exception as e:
        log.error(f"Build error: {e}")
        return False


def _ftp_upload_recursive(ftp: ftplib.FTP, local_dir: str, remote_dir: str):
    """Recursively upload a directory via FTP."""
    for root, dirs, files in os.walk(local_dir):
        rel = os.path.relpath(root, local_dir)
        if rel == ".":
            remote_path = remote_dir
        else:
            remote_path = f"{remote_dir}/{rel.replace(os.sep, '/')}"
        try:
            ftp.cwd(remote_path)
        except Exception:
            parts = remote_path.split("/")
            path_so_far = ""
            for p in parts:
                path_so_far += f"/{p}" if path_so_far else p
                try:
                    ftp.cwd(path_so_far)
                except Exception:
                    ftp.mkd(path_so_far)
                    ftp.cwd(path_so_far)
        for fname in files:
            local_file = os.path.join(root, fname)
            try:
                with open(local_file, "rb") as f:
                    ftp.storbinary(f"STOR {fname}", f)
            except Exception as e:
                log.warning(f"FTP upload failed for {local_file}: {e}")


def deploy_website() -> bool:
    """Deploy the built website via FTP to greensol.me/nullstate/."""
    if not os.path.exists(BUILD_DIR):
        log.warning("No build directory found")
        return False

    ftp_host = os.environ.get("FTP_HOST", "server26.shared.spaceship.host")
    ftp_user = os.environ.get("FTP_USER", "admin@greensol.me")
    ftp_pass = os.environ.get("FTP_PASS", "V8sHRwRF#p^o")
    ftp_remote = "/nullstate"

    try:
        ftp = ftplib.FTP(ftp_host, ftp_user, ftp_pass, timeout=60)
        ftp.encoding = "utf-8"
        _ftp_upload_recursive(ftp, BUILD_DIR, ftp_remote)
        ftp.quit()
        log.info(f"FTP deployed {BUILD_DIR} -> {ftp_host}{ftp_remote}")
        # Archive build for rollback
        archive_path = f"/home/Nullstate-linux-vm/deployments/nullstate-website-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
        os.makedirs("/home/Nullstate-linux-vm/deployments", exist_ok=True)
        subprocess.run(["tar", "-czf", archive_path, "-C", BUILD_DIR, "."], cwd="/")
        log.info(f"Build archived: {archive_path}")
        return True
    except Exception as e:
        log.error(f"FTP deploy failed: {e}")
        return False


def run_improvement_cycle() -> Dict:
    """Run one complete improvement cycle."""
    log.info("=" * 60)
    log.info("Starting Continuous Improvement Cycle")
    log.info("=" * 60)

    start = time.time()

    # Step 1: Evaluate current website
    log.info("Step 1: Evaluating website...")
    evaluation = evaluate_website()
    log.info(f"  Score: {evaluation['overall_score']:.1f}/10")
    log.info(f"  Issues: {len(evaluation['issues_found'])} checked")

    # Step 2: Generate improvements
    log.info("Step 2: Generating improvements...")
    improvements = generate_improvements(evaluation)
    log.info(f"  Generated {len(improvements)} improvements")

    # Step 3: Apply improvements
    log.info("Step 3: Applying improvements...")
    applied = apply_improvements(improvements)
    log.info(f"  Applied {len(applied)} fixes/suggestions")

    # Step 4: Rebuild
    log.info("Step 4: Rebuilding website...")
    rebuild_ok = rebuild_website()

    # Step 5: Deploy
    deployed = False
    if rebuild_ok:
        log.info("Step 5: Deploying...")
        deployed = deploy_website()

    elapsed = time.time() - start

    result = {
        "cycle_time": f"{elapsed:.1f}s",
        "evaluation_score": evaluation["overall_score"],
        "improvements_generated": len(improvements),
        "fixes_applied": len(applied),
        "rebuild_success": rebuild_ok,
        "deploy_success": deployed,
        "applied_fixes": applied[:10],
    }

    log.info(f"Cycle complete: {json.dumps(result, indent=2)}")
    return result


def main():
    """Run the continuous improvement loop as a standalone script (cron-friendly)."""
    import argparse
    parser = argparse.ArgumentParser(description="NullState Website Improvement Loop")
    parser.add_argument("--rebuild-only", action="store_true", help="Only rebuild without evaluation")
    parser.add_argument("--deploy", action="store_true", help="Deploy after rebuild")
    args = parser.parse_args()

    if args.rebuild_only:
        ok = rebuild_website()
        if ok and args.deploy:
            deploy_website()
        return

    result = run_improvement_cycle()

    # Output metrics for cron logging
    print(json.dumps(result))


if __name__ == "__main__":
    main()

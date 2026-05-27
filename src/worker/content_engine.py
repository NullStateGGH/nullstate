"""NullState Content Engine — Automated blog content generator.

Uses Gemini 2.5 Flash to generate SEO-optimized blog posts about
the agent economy, AI payments, and NullState. Runs as a cron job.
"""

import json
import os
import re
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

WEBSITE_DIR = Path("/home/Nullstate-linux-vm/nullstate-website")
BLOG_DIR = WEBSITE_DIR / "blog"
GEMINI_API_KEY = os.environ.get("NULLSTATE_GOOGLE_API_KEY", "")
DEPLOY_SCRIPT = str(Path("/home/Nullstate-linux-vm") / "deploy_content.sh")

TOPICS = [
    "Why AI agents need their own payment infrastructure (not Stripe, not PayPal)",
    "HTTP 402 is finally useful: How x402 is changing machine-to-machine payments",
    "Know Your Agent: Why identity matters more than KYC in the agent economy",
    "Running a production AI payment gateway on a $20/month VPS",
    "The $93B agent economy opportunity that nobody is talking about",
    "AP2 protocol: How RSA-2048 dual-signing enables trustless agent commerce",
    "From zero to gateway: Deploying NullState in 30 seconds",
    "MCP ecosystem growth: Why Model Context Protocol is the TCP/IP of AI agents",
    "Self-hosted vs SaaS: Why AI agents need decentralized payment infrastructure",
    "Telemetry-driven development: How we use AI to improve our AI payment system",
]

def generate_post(topic: str) -> tuple[str, str, str, list[str]]:
    """Generate a full blog post using Gemini. Returns (slug, title, content, tags)."""
    prompt = f"""Write a blog article for NullState (open-source payment infrastructure for AI agents) on this topic:
{topic}

Format as a Docusaurus MDX blog post with frontmatter:
- slug: kebab-case-url
- title: compelling headline under 80 chars
- tags: list of 3-5 relevant tags from [ai-agents, payments, x402, AP2, MCP, KYA, engineering, infrastructure, protocol, open-source, tutorial, analysis, opinion]

Include the <!-- truncate --> tag after the intro paragraph.
Write in a confident, direct voice. No fluff. No buzzwords. Keep it under 800 words.
Include real technical details and specific metrics where plausible.

Return ONLY valid MDX content starting with '---'."""
    
    def _call_gemini(model: str) -> dict:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.8, "maxOutputTokens": 2048}
            },
            timeout=30
        )
        return resp.json()

    try:
        data = _call_gemini("gemini-2.5-flash")
        if "candidates" not in data:
            data = _call_gemini("gemini-2.0-flash")
        if "candidates" not in data:
            data = _call_gemini("gemini-1.5-flash-002")
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        
        # Parse frontmatter
        frontmatch = re.match(r'^---\n(.*?)\n---\n(.*)', text, re.DOTALL)
        if not frontmatch:
            return None, None, None, None
        
        frontmatter = frontmatch.group(1)
        body = frontmatch.group(2)
        
        # Extract slug
        slug_match = re.search(r'slug:\s*(\S+)', frontmatter)
        slug = slug_match.group(1) if slug_match else f"post-{int(time.time())}"
        
        # Extract title and ensure it's quoted
        title_match = re.search(r'title:\s*["\']?(.*?)["\']?\n', frontmatter)
        title = title_match.group(1) if title_match else topic[:80]
        content = re.sub(r'^title:\s*(.*)$', lambda m: f'title: "{m.group(1).strip()}"', content, flags=re.MULTILINE)
        
        # Extract tags
        tags_match = re.search(r'tags:\s*\[(.*?)\]', frontmatter)
        tags = [t.strip().strip('"\'') for t in tags_match.group(1).split(',')] if tags_match else []
        
        # Convert HTML comment to MDX comment
        body = body.replace('<!-- truncate -->', '{/* truncate */}')
        
        content = f"---\n{frontmatter}\n---\n\n{body.strip()}\n"
        
        return slug, title, content, tags
        
    except Exception as e:
        print(f"[content] Error generating post: {e}")
        return None, None, None, None


def save_post(slug: str, content: str) -> bool:
    """Save generated post to blog directory."""
    if not slug or not content:
        return False
    
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{date}-{slug}.md"
    filepath = BLOG_DIR / filename
    
    # Don't overwrite existing posts
    if filepath.exists():
        print(f"[content] Post already exists: {filename}")
        return False
    
    filepath.write_text(content)
    print(f"[content] Saved: {filename}")
    return True


def rebuild_and_deploy():
    """Build and deploy the website after content changes."""
    import subprocess
    try:
        # Build
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(WEBSITE_DIR),
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode != 0:
            print(f"[content] Build failed: {result.stderr[-500:]}")
            return False
        
        # Deploy via FTP
        result = subprocess.run(
            ["lftp", "-e", "set ftp:ssl-allow true; mirror -R build/ /nullstate/ --parallel=5 --delete --ignore-time; quit",
             "-u", "admin@greensol.me,V8sHRwRF#p^o", "server26.shared.spaceship.host"],
            cwd=str(WEBSITE_DIR),
            capture_output=True,
            text=True,
            timeout=180
        )
        if result.returncode != 0:
            print(f"[content] Deploy failed: {result.stderr[-500:]}")
            return False
        
        print("[content] Rebuild and deploy complete")
        return True
    except Exception as e:
        print(f"[content] Deploy error: {e}")
        return False


def generate_batch(count: int = 3):
    """Generate and publish multiple posts."""
    available = [t for t in TOPICS if t not in _get_published_topics()]
    if not available:
        print("[content] No new topics available — all published")
        return 0
    
    success = 0
    for topic in available[:count]:
        print(f"[content] Generating: {topic[:60]}...")
        slug, title, content, tags = generate_post(topic)
        if save_post(slug, content):
            success += 1
        time.sleep(2)  # Rate limit between API calls
    
    if success > 0:
        rebuild_and_deploy()
    
    return success


def _get_published_topics() -> set:
    """Get set of topics already published as blog posts."""
    published = set()
    for f in BLOG_DIR.glob("*.md"):
        content = f.read_text()
        # Look for title in frontmatter
        match = re.search(r'title:\s*["\']?(.*?)["\']?\n', content)
        if match:
            published.add(match.group(1).lower())
    return published


if __name__ == "__main__":
    count = generate_batch(int(os.environ.get("BATCH_SIZE", "3")))
    print(f"[content] Generated and published {count} new posts")

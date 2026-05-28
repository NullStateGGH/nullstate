"""NullState Global Ecosystem Feedback Engine.
Autonomous web intelligence, social listening, market analysis, and ecosystem integration.
Feeds continuous real-world data back into NullState for adaptation and growth.

Data Sources (zero API key needed):
  - Google Gemini (intelligent search/reasoning agent)
  - Hacker News API (free, no auth)
  - GitHub Trending (public scrape)
  - Reddit public JSON
  - News/RSS feeds
  - MCP ecosystem (hub discovery)
  - AI directories
  - Package registries (PyPI, npm)
  - Web scraping
"""

import os
import json
import time
import logging
import sqlite3
import requests
import hashlib
import threading
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from html.parser import HTMLParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [GLOBAL_FEEDBACK] %(message)s")
log = logging.getLogger("nullstate-global-feedback")

GEMINI_API_KEY = os.environ.get("NULLSTATE_GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DB_PATH = os.environ.get("NULLSTATE_DB_PATH", "src/core/nullstate.db")
WEBSITE_DIR = "/home/Nullstate-linux-vm/nullstate-website"
BACKUP_DIR = "/home/Nullstate-linux-vm/backups"

GATEWAY_URL = os.environ.get("GATEWAY_URL", "https://localhost:8080")

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
GITHUB_API_BASE = "https://api.github.com"
REDDIT_API_BASE = "https://www.reddit.com"

ECOSYSTEM_INDICATORS = [
    "AI agent payments", "MCP protocol", "x402 HTTP 402", "agent economy",
    "autonomous AI revenue", "agent-to-agent payments", "AI API monetization",
    "machine learning infrastructure", "open source AI payments",
    "agentic automation", "LLM function calling", "AI tool ecosystem",
]
COMPETITOR_KEYWORDS = [
    "LangChain", "AutoGPT", "CrewAI", "Fixie", "Vercel AI SDK",
    "Anthropic MCP", "OpenAI function calling", "Coinbase CDP",
    "Crossmint", "Worldcoin", "Hedera", "Solana Pay",
]
MONITORED_PACKAGES = ["nullstate", "nullstate-cli", "nullstate-sdk"]

DT = "  "


class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
    def handle_data(self, data):
        self.text.append(data)
    def get_text(self):
        return " ".join(self.text)


def strip_html(html: str) -> str:
    s = HTMLStripper()
    s.feed(html)
    return s.get_text()


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ecosystem_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT, signal_type TEXT, title TEXT, url TEXT,
            summary TEXT, relevance_score REAL, sentiment TEXT,
            topic TEXT, raw_data TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS adaptation_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER, decision TEXT, reasoning TEXT,
            action_taken TEXT, status TEXT DEFAULT 'pending',
            timestamp TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS ecosystem_communication (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT, channel TEXT, message_type TEXT,
            content TEXT, target_url TEXT, status TEXT DEFAULT 'pending',
            result TEXT, timestamp TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS market_intelligence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT, indicator TEXT, value REAL,
            change_7d REAL, change_30d REAL, source TEXT,
            metadata TEXT, timestamp TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


def call_gemini(prompt: str, temperature: float = 0.3, max_tokens: int = 1024) -> Optional[str]:
    if not GEMINI_API_KEY:
        log.warning("No Gemini API key — falling back to Ollama")
        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/generate",
                json={"model": os.environ.get("NULLSTATE_MODEL", "nullstate"),
                      "prompt": prompt, "temperature": temperature,
                      "max_tokens": max_tokens, "stream": False},
                timeout=300
            )
            return resp.json().get("response") if resp.status_code == 200 else None
        except Exception:
            return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        resp = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}
        }, timeout=30)
        if resp.status_code == 200:
            candidates = resp.json().get("candidates", [])
            if candidates:
                return candidates[0]["content"]["parts"][0]["text"]
    except Exception as e:
        log.debug(f"Gemini call failed: {e}")
    return None


def store_signal(source: str, signal_type: str = "", title: str = "", url: str = "",
                 summary: str = "", relevance: float = 0.5, sentiment: str = "neutral",
                 topic: str = "", raw: str = "", type: str = ""):
    if not signal_type and type:
        signal_type = type
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO ecosystem_signals (source, signal_type, title, url, summary, relevance_score, sentiment, topic, raw_data) VALUES (?,?,?,?,?,?,?,?,?)",
            (source, signal_type, title[:500], url[:2000], summary[:2000],
             round(relevance, 3), sentiment, topic[:200], raw[:5000])
        )
        conn.commit()
        conn.close()
        log.info(f"Signal stored: [{source}] {title[:60]}... (relevance={relevance})")
    except Exception as e:
        log.error(f"Signal store failed: {e}")


def store_market_indicator(category: str, indicator: str, value: float,
                           change_7d: float = 0, change_30d: float = 0,
                           source: str = "", metadata: str = ""):
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO market_intelligence (category, indicator, value, change_7d, change_30d, source, metadata) VALUES (?,?,?,?,?,?,?)",
            (category, indicator, round(value, 6), round(change_7d, 6),
             round(change_30d, 6), source, metadata[:2000])
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"Market indicator store failed: {e}")


# ─── Phase 1: Web Intelligence ─────────────────────────────────────────


def scan_hacker_news() -> List[Dict]:
    """Scrape Hacker News for AI agent / payment ecosystem signals."""
    signals = []
    try:
        story_ids = requests.get(f"{HN_API_BASE}/topstories.json", timeout=10).json()[:50]
        _batch = requests.post(f"{HN_API_BASE}/items.json", json=story_ids, timeout=10).json() if False else []
        for sid in story_ids[:30]:
            try:
                item = requests.get(f"{HN_API_BASE}/item/{sid}.json", timeout=5).json()
                if not item or item.get("type") != "story":
                    continue
                title = item.get("title", "")
                url = item.get("url", f"https://news.ycombinator.com/item?id={sid}")
                text = item.get("text", "")
                combined = (title + " " + text).lower()
                keywords = ["ai agent", "payment", "mcp", "protocol", "api", "autonomous",
                            "llm", "function calling", "agent", "settlement", "crypto",
                            "micropayment", "HTTP 402", "x402", "token", "model"]
                if any(k in combined for k in keywords):
                    relevance = sum(2 for k in keywords if k in combined) / len(keywords)
                    signals.append({
                        "source": "hacker_news",
                        "type": "discussion",
                        "title": title[:200],
                        "url": url[:500],
                        "summary": strip_html(text)[:500] if text else title[:200],
                        "relevance": min(relevance, 1.0),
                        "sentiment": "positive" if any(w in combined for w in ["launch", "open source", "funding", "growth"]) else "neutral",
                        "topic": next((k for k in keywords if k in combined), "general"),
                    })
            except Exception:
                continue
        log.info(f"Hacker News: {len(signals)} relevant stories")
    except Exception as e:
        log.warning(f"HN scan failed: {e}")
    return signals


def scan_github_trending() -> List[Dict]:
    """Scrape GitHub trending repositories for ecosystem intelligence."""
    signals = []
    try:
        repos = requests.get(f"{GITHUB_API_BASE}/search/repositories?q=AI+agent+payment&sort=stars&order=desc&per_page=20",
                             headers={"Accept": "application/vnd.github.v3+json"},
                             timeout=10).json().get("items", [])
        for repo in repos[:10]:
            desc = repo.get("description", "") or ""
            combined = (repo["name"] + " " + desc).lower()
            if any(k in combined for k in ["agent", "payment", "mcp", "x402", "protocol", "llm", "ai"]):
                signals.append({
                    "source": "github_trending",
                    "type": "repository",
                    "title": repo["full_name"],
                    "url": repo["html_url"],
                    "summary": desc[:300],
                    "relevance": 0.6,
                    "sentiment": "positive",
                    "topic": "ecosystem_growth",
                })
        log.info(f"GitHub: {len(signals)} relevant repos")
    except Exception as e:
        log.warning(f"GitHub scan failed: {e}")
    return signals


def scan_reddit() -> List[Dict]:
    """Scrape Reddit for AI agent payment discussions."""
    signals = []
    subreddits = ["artificial", "MachineLearning", "ClaudeAI", "OpenAI",
                   "LocalLLaMA", "alphaai", "sideproject", "SaaS"]
    search_terms = ["AI agent payment", "MCP protocol", "agent economy",
                    "HTTP 402", "x402", "AI API monetization"]
    try:
        for sub in subreddits:
            try:
                data = requests.get(
                    f"{REDDIT_API_BASE}/r/{sub}/hot.json?limit=15",
                    headers={"User-Agent": "NullState/1.0"},
                    timeout=10
                ).json()
                for post in data.get("data", {}).get("children", []):
                    d = post["data"]
                    title = d.get("title", "")
                    combined = (title + " " + (d.get("selftext", "") or "")).lower()
                    matches = [t for t in search_terms if t.lower() in combined]
                    if matches:
                        signals.append({
                            "source": f"reddit_r_{sub}",
                            "type": "discussion",
                            "title": title[:200],
                            "url": f"https://reddit.com{d['permalink']}" if d.get("permalink") else "",
                            "summary": strip_html(d.get("selftext", "") or "")[:400],
                            "relevance": min(len(matches) * 0.3, 1.0),
                            "sentiment": "positive" if any(w in combined for w in ["awesome", "love", "solution", "open source"]) else "neutral",
                            "topic": matches[0] if matches else "general",
                        })
            except Exception:
                continue
        log.info(f"Reddit: {len(signals)} relevant posts")
    except Exception as e:
        log.warning(f"Reddit scan failed: {e}")
    return signals


def scan_ai_directories() -> List[Dict]:
    """Check AI tool directories for NullState presence and competitor listings."""
    signals = []
    directories = [
        ("Toolify", "https://toolify.ai/search?q=nullstate"),
        ("There's An AI For That", "https://theresanaiforthat.com/s/payment/"),
        ("Futurepedia", "https://www.futurepedia.io/search?q=AI+payment"),
        ("Easy With AI", "https://easywithai.com/search/agent+payment/"),
    ]
    for name, url in directories:
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                text = resp.text.lower()
                found = "nullstate" in text or "nullstate" in url.lower()
                signals.append({
                    "source": "ai_directory",
                    "type": "listing_check",
                    "title": f"NullState presence on {name}",
                    "url": url,
                    "summary": f"Listed: {found}" if found else f"Not listed on {name}",
                    "relevance": 0.7 if found else 0.9,
                    "sentiment": "positive" if found else "neutral",
                    "topic": "ecosystem_presence",
                })
        except Exception:
            continue
    log.info(f"AI Directories: {len(signals)} checks")
    return signals


def scan_news_feeds() -> List[Dict]:
    """Scrape RSS/news sources for AI agent payment ecosystem news."""
    signals = []
    feeds = [
        ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
        ("The Decoder", "https://the-decoder.com/feed/"),
        ("Hacker News", "https://hnrss.org/frontpage"),
    ]
    for name, feed_url in feeds:
        try:
            resp = requests.get(feed_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.content)
                ns = {"atom": "http://www.w3.org/2005/Atom",
                      "rss": "http://purl.org/rss/1.0/",
                      "content": "http://purl.org/rss/1.0/modules/content/"}
                items = []
                for item in root.iter("item") or root.findall(".//atom:entry", ns):
                    title = item.findtext("title", "") or item.findtext("atom:title", "", ns)
                    link = item.findtext("link", "") or item.findtext("atom:link", "", ns)
                    desc = item.findtext("description", "") or item.findtext("atom:summary", "", ns)
                    items.append((title, link, desc))
                for title, link, desc in items[:5]:
                    combined = (title + " " + desc).lower()
                    if any(k in combined for k in ["ai", "agent", "payment", "mcp",
                                                    "protocol", "llm", "autonomous",
                                                    "open source"]):
                        signals.append({
                            "source": f"news_{name}",
                            "type": "news",
                            "title": title[:200],
                            "url": link[:500] if link else "",
                            "summary": strip_html(desc)[:400],
                            "relevance": 0.5,
                            "sentiment": "neutral",
                            "topic": "industry_news",
                        })
        except Exception:
            continue
    log.info(f"News feeds: {len(signals)} relevant articles")
    return signals


def scan_ecosystem_indicators() -> List[Dict]:
    """Use Gemini to analyze market position and ecosystem trends."""
    signals = []
    for indicator in ECOSYSTEM_INDICATORS[:5]:
        prompt = f"""Analyze the current state of "{indicator}" in the AI ecosystem (2026).
Provide a brief market intelligence report with:
1. Current maturity level (emerging/growing/mature)
2. Key companies/projects involved
3. Recent developments (last 30 days)
4. Growth trajectory
5. How NullState (open source AI payment/settlement layer) is positioned
Focus on factual, actionable intelligence."""
        result = call_gemini(prompt, temperature=0.2, max_tokens=600)
        if result:
            signals.append({
                "source": "gemini_market_intel",
                "type": "market_analysis",
                "title": f"Market intelligence: {indicator}",
                "url": "",
                "summary": result[:800],
                "relevance": 0.8,
                "sentiment": "neutral",
                "topic": indicator[:100],
            })
            store_market_indicator("ecosystem_trend", indicator, 1.0, source="gemini_analysis", metadata=result[:500])
            time.sleep(1)
    log.info(f"Ecosystem indicators: {len(signals)} analyses")
    return signals


def scan_mcp_ecosystem() -> List[Dict]:
    """Check MCP ecosystem via local hub for growth indicators."""
    signals = []
    try:
        resp = requests.get("http://localhost:8090/hub/servers", timeout=5)
        if resp.status_code == 200:
            servers = resp.json()
            count = len(servers) if isinstance(servers, list) else 0
            signals.append({
                "source": "mcp_hub",
                "type": "ecosystem_size",
                "title": f"MCP ecosystem: {count} servers",
                "url": "http://localhost:8090/hub/servers",
                "summary": f"NullState MCP Hub discovered {count} servers in the MCP ecosystem",
                "relevance": 0.6,
                "sentiment": "positive" if count > 0 else "neutral",
                "topic": "mcp_ecosystem",
            })
            store_market_indicator("mcp", "servers_discovered", count, source="mcp_hub")
    except Exception:
        signals.append({
            "source": "mcp_hub",
            "type": "ecosystem_size",
            "title": "MCP Hub unreachable",
            "url": "",
            "summary": "MCP Hub not responding — may not be running",
            "relevance": 0.3,
            "sentiment": "neutral",
            "topic": "infrastructure",
        })
    log.info(f"MCP ecosystem: {len(signals)} signals")
    return signals


# ─── Phase 2: Competitor Intelligence ──────────────────────────────────


def scan_competitors() -> List[Dict]:
    """Monitor competitor landscape via Gemini analysis."""
    signals = []
    prompt = f"""Analyze the competitive landscape for AI agent payment/settlement infrastructure (2026).
For each of these competitors/projects, provide a brief update on recent developments:
{', '.join(COMPETITOR_KEYWORDS)}

For each:
1. Recent news (last 30 days)
2. Funding/valuation if applicable
3. Key product launches
4. Threat level to NullState (low/medium/high)
5. What NullState can learn from them

Output as a structured analysis with clear sections per competitor."""
    result = call_gemini(prompt, temperature=0.2, max_tokens=1200)
    if result:
        signals.append({
            "source": "gemini_competitor_intel",
            "type": "competitor_analysis",
            "title": "Competitor landscape analysis",
            "url": "",
            "summary": result[:1500],
            "relevance": 0.9,
            "sentiment": "neutral",
            "topic": "competitive_intelligence",
        })
    log.info(f"Competitor analysis: {1 if result else 0} signals")
    return signals


# ─── Phase 3: Ecosystem Presence ──────────────────────────────────────


def check_package_registries() -> List[Dict]:
    """Check NullState presence on PyPI, npm, and other registries."""
    signals = []
    for pkg in MONITORED_PACKAGES:
        try:
            resp = requests.get(f"https://pypi.org/pypi/{pkg}/json", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                info = data.get("info", {})
                _downloads = data.get("urls", [])
                signals.append({
                    "source": "pypi",
                    "type": "package_stats",
                    "title": f"PyPI: {pkg} v{info.get('version', '?')}",
                    "url": f"https://pypi.org/project/{pkg}/",
                    "summary": f"Summary: {info.get('summary', '')[:200]}",
                    "relevance": 0.5,
                    "sentiment": "positive",
                    "topic": "ecosystem_presence",
                })
                store_market_indicator("package", f"pypi_{pkg}_exists", 1.0, source="pypi")
            else:
                signals.append({
                    "source": "pypi",
                    "type": "package_stats",
                    "title": f"PyPI: {pkg} not found",
                    "url": "",
                    "summary": f"Package {pkg} not published on PyPI",
                    "relevance": 0.8,
                    "sentiment": "neutral",
                    "topic": "ecosystem_gap",
                })
                store_market_indicator("package", f"pypi_{pkg}_exists", 0.0, source="pypi")
        except Exception:
            continue
    log.info(f"Package registries: {len(signals)} checks")
    return signals


def check_website_seo() -> List[Dict]:
    """Check website SEO health and search engine presence."""
    signals = []
    checks = [
        ("Google Index", "https://www.google.com/search?q=site:greensol.me+nullstate"),
        ("Sitemap", "https://greensol.me/nullstate/sitemap.xml"),
        ("Robots", "https://greensol.me/nullstate/robots.txt"),
        ("LLMs.txt", "https://greensol.me/nullstate/llms.txt"),
    ]
    for name, url in checks:
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            status = "accessible" if resp.status_code == 200 else f"HTTP {resp.status_code}"
            signals.append({
                "source": "seo_check",
                "type": "seo_health",
                "title": f"SEO: {name} — {status}",
                "url": url,
                "summary": f"{name} returned {status}",
                "relevance": 0.4,
                "sentiment": "positive" if resp.status_code == 200 else "neutral",
                "topic": "seo",
            })
            store_market_indicator("seo", name, 1.0 if resp.status_code == 200 else 0.0, source="seo_check")
        except Exception as e:
            signals.append({
                "source": "seo_check",
                "type": "seo_health",
                "title": f"SEO: {name} — error",
                "url": url,
                "summary": f"Check failed: {e}",
                "relevance": 0.4,
                "sentiment": "neutral",
                "topic": "seo",
            })
    log.info(f"SEO checks: {len(signals)} results")
    return signals


# ─── Phase 4: Communication & Engagement ──────────────────────────────


def generate_communication_opportunities(signals: List[Dict]) -> List[Dict]:
    """Analyze signals and identify where NullState should engage."""
    opportunities = []
    high_relevance = [s for s in signals if s.get("relevance", 0) > 0.6]
    if not high_relevance:
        return opportunities
    summaries = "\n".join([f"- {s['source']}: {s['title'][:80]}" for s in high_relevance[:10]])

    prompt = f"""You are NullState's autonomous communication strategist.
Analyze these ecosystem signals and identify WHERE and HOW NullState should engage:

{summaries}

For the top 3 opportunities, provide:
1. Platform/channel (where to engage)
2. Message type (comment, post, PR, issue, question)
3. Key message / talking points
4. Urgency (immediate/this week/this month)
5. Expected impact (low/medium/high)

Focus on the agent payment ecosystem. NullState is an open-source payment/settlement layer for AI agents.
Be specific and actionable."""
    result = call_gemini(prompt, temperature=0.3, max_tokens=800)
    if result:
        try:
            conn = get_db()
            conn.execute(
                "INSERT INTO ecosystem_communication (platform, channel, message_type, content, status) VALUES (?,?,?,?,?)",
                ("gemini_strategy", "cross_platform", "engagement_plan", result[:2000], "pending")
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
        opportunities.append({
            "source": "communication_strategy",
            "type": "engagement_plan",
            "title": "Communication opportunities identified",
            "url": "",
            "summary": result[:1000],
            "relevance": 0.9,
            "sentiment": "positive",
            "topic": "community_engagement",
        })
    return opportunities


def generate_market_report(signals: List[Dict]) -> str:
    """Generate a comprehensive market intelligence report from all signals."""
    if not signals:
        return ""
    summary_data = defaultdict(list)
    for s in signals:
        summary_data[s.get("source", "unknown")].append(s)

    report_sections = []
    report_sections.append("# NullState Ecosystem Intelligence Report")
    report_sections.append(f"*Generated: {datetime.now(timezone.utc).isoformat()}*\n")
    report_sections.append("## Overview")
    report_sections.append(f"Total signals collected: {len(signals)}")
    report_sections.append(f"Sources: {', '.join(sorted(summary_data.keys()))}\n")

    for source, sigs in sorted(summary_data.items()):
        report_sections.append(f"\n## Source: {source}")
        report_sections.append(f"Signals: {len(sigs)}")
        avg_relevance = sum(s.get("relevance", 0) for s in sigs) / len(sigs) if sigs else 0
        report_sections.append(f"Avg relevance: {avg_relevance:.2f}")
        for s in sigs[:5]:
            report_sections.append(f"- [{s.get('type','')}] {s['title']}")
            if s.get("summary"):
                report_sections.append(f"  {s['summary'][:200]}")

    report = "\n".join(report_sections)
    report_path = Path(f"{WEBSITE_DIR}/static/market_intelligence.md")
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report)
        log.info(f"Market report saved to {report_path}")
    except Exception as e:
        log.error(f"Report save failed: {e}")
    return report


def generate_adaptation_decisions(signals: List[Dict]) -> List[Dict]:
    """Analyze signals and generate adaptation decisions for the HOD engine."""
    decisions = []
    high_signals = [s for s in signals if s.get("relevance", 0) > 0.7]
    if not high_signals:
        return decisions

    signal_summary = "\n".join([f"[{s['source']}] {s['title'][:100]}" for s in high_signals[:8]])
    prompt = f"""You are NullState's autonomous adaptation engine.
Based on these ecosystem signals, recommend up to 3 concrete actions NullState should take to adapt and grow:

{signal_summary}

For each action, provide:
1. Decision (what to do — be specific)
2. Reasoning (why this matters)
3. Action type: one of [code_change, content_create, deploy, config_change, research, outreach]
4. Priority: 1-5 (1=urgent, 5=whenever)

Example decisions:
- "Add MCP server directory submission to deploy pipeline"
- "Create blog post about X402 vs traditional payment APIs"
- "Fix canonical URL in Docusaurus config"
- "Add Reddit monitoring to feedback loop"
- "Publish NullState package to PyPI"

Output as JSON array of {{"decision": "...", "reasoning": "...", "action_type": "...", "priority": N}}"""
    result = call_gemini(prompt, temperature=0.2, max_tokens=1000)
    if result:
        try:
            import re
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                for dec in parsed:
                    try:
                        conn = get_db()
                        conn.execute(
                            "INSERT INTO adaptation_decisions (signal_id, decision, reasoning, action_taken, status) VALUES (?,?,?,?,?)",
                            (0, dec.get("decision", "")[:300], dec.get("reasoning", "")[:500],
                             dec.get("action_type", "")[:100], "pending")
                        )
                        conn.commit()
                        conn.close()
                        decisions.append(dec)
                    except Exception:
                        continue
        except Exception:
            pass
    log.info(f"Adaptation decisions: {len(decisions)} generated")
    return decisions


# ─── Main Cycle ────────────────────────────────────────────────────────


def run_global_feedback_cycle() -> Dict:
    """Run the complete global ecosystem feedback cycle."""
    cycle_id = f"gfb_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    log.info(f"\n{'='*60}\nGlobal Feedback Cycle {cycle_id}\n{'='*60}")
    start = time.time()
    all_signals = []

    log.info("\nPhase 1: Web Intelligence — scanning 6 sources...")
    for scanner_name, scanner_fn in [
        ("Hacker News", scan_hacker_news),
        ("GitHub Trending", scan_github_trending),
        ("Reddit", scan_reddit),
        ("AI Directories", scan_ai_directories),
        ("News Feeds", scan_news_feeds),
        ("MCP Ecosystem", scan_mcp_ecosystem),
    ]:
        try:
            sigs = scanner_fn()
            for s in sigs:
                store_signal(**s)
            all_signals.extend(sigs)
            log.info(f"  {scanner_name}: {len(sigs)} signals")
        except Exception as e:
            log.warning(f"  {scanner_name}: error - {e}")

    log.info("\nPhase 2: Market Intelligence — ecosystem analysis...")
    try:
        indicators = scan_ecosystem_indicators()
        for s in indicators:
            store_signal(**s)
        all_signals.extend(indicators)
    except Exception as e:
        log.warning(f"Market intel: {e}")

    log.info("\nPhase 3: Competitor Intelligence...")
    try:
        comp = scan_competitors()
        for s in comp:
            store_signal(**s)
        all_signals.extend(comp)
    except Exception as e:
        log.warning(f"Competitor scan: {e}")

    log.info("\nPhase 4: Ecosystem Presence...")
    for scanner_name, scanner_fn in [
        ("Package Registries", check_package_registries),
        ("Website SEO", check_website_seo),
    ]:
        try:
            sigs = scanner_fn()
            for s in sigs:
                store_signal(**s)
            all_signals.extend(sigs)
            log.info(f"  {scanner_name}: {len(sigs)} signals")
        except Exception as e:
            log.warning(f"  {scanner_name}: error - {e}")

    log.info("\nPhase 5: Generating adaptation decisions...")
    decisions = generate_adaptation_decisions(all_signals)

    log.info("\nPhase 6: Communication strategy...")
    opportunities = generate_communication_opportunities(all_signals)

    log.info("\nPhase 7: Market report...")
    report = generate_market_report(all_signals)

    elapsed = time.time() - start
    result = {
        "cycle_id": cycle_id,
        "signals_collected": len(all_signals),
        "decisions_generated": len(decisions),
        "opportunities_found": len(opportunities),
        "report_length": len(report),
        "sources": list(set(s.get("source", "unknown") for s in all_signals)),
        "elapsed_seconds": round(elapsed, 1),
    }

    log.info(f"\n{'='*60}")
    log.info(f"Cycle complete: {result['signals_collected']} signals, {result['decisions_generated']} decisions")
    log.info(f"Sources: {', '.join(result['sources'])}")
    log.info(f"Elapsed: {result['elapsed_seconds']}s")
    log.info(f"{'='*60}")
    return result


def apply_top_decisions(decisions: List[Dict]) -> List[str]:
    """Apply the top priority adaptation decisions automatically."""
    applied = []
    sorted_dec = sorted(decisions, key=lambda d: d.get("priority", 5))[:2]
    for dec in sorted_dec:
        action = dec.get("action_type", "")
        decision_text = dec.get("decision", "").lower()
        try:
            if action == "content_create" or "blog" in decision_text or "post" in decision_text:
                topic = decision_text.replace("blog post about", "").replace("create", "").strip()
                prompt = f"Write a 400-word technical blog post about: {topic}. Target audience: AI developers. Include actionable insights."
                content = call_gemini(prompt, temperature=0.4, max_tokens=800)
                if content:
                    blog_dir = Path(f"{WEBSITE_DIR}/blog")
                    blog_dir.mkdir(parents=True, exist_ok=True)
                    date_str = datetime.now().strftime("%Y-%m-%d")
                    slug = re.sub(r'[^a-z0-9]+', '-', topic.lower())[:40]
                    filepath = blog_dir / f"{date_str}-global-feedback-{slug}.md"
                    header = f"---\nslug: global-feedback-{slug}\ntitle: {topic.title()}\nauthors: [hod]\ntags: [ecosystem, ai, automatic]\n---\n\n"
                    filepath.write_text(header + content)
                    applied.append(f"Blog post created: {topic}")
                    log.info(f"Auto-generated blog: {filepath}")

            elif action == "config_change" or "config" in decision_text or "fix" in decision_text:
                applied.append(f"Config change noted: {dec.get('decision', '')[:80]}")

            elif action == "deploy" or "submit" in decision_text or "publish" in decision_text:
                applied.append(f"Deploy task noted: {dec.get('decision', '')[:80]}")

            elif action == "research" or "monitor" in decision_text or "track" in decision_text:
                applied.append(f"Monitoring task noted: {dec.get('decision', '')[:80]}")

            if not applied or applied[-1] != action:
                applied.append(f"Decision queued: {dec.get('decision', '')[:80]}")

            conn = get_db()
            conn.execute("UPDATE adaptation_decisions SET status = 'applied' WHERE decision = ?",
                         (dec.get("decision", "")[:300],))
            conn.commit()
            conn.close()
        except Exception as e:
            log.warning(f"Could not apply decision '{dec.get('decision', '')[:40]}': {e}")
    return applied


def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="NullState Global Ecosystem Feedback Engine")
    parser.add_argument("--cycle", action="store_true", help="Run one complete feedback cycle")
    parser.add_argument("--signals", action="store_true", help="Show recent signals")
    parser.add_argument("--decisions", action="store_true", help="Show pending adaptation decisions")
    parser.add_argument("--apply", action="store_true", help="Run cycle and apply top decisions")
    parser.add_argument("--continuous", type=float, default=0, help="Run continuous with interval hours")
    args = parser.parse_args()

    if args.signals:
        conn = get_db()
        rows = conn.execute("SELECT source, signal_type, title, relevance_score, timestamp FROM ecosystem_signals ORDER BY id DESC LIMIT 20").fetchall()
        conn.close()
        print(f"\n{'Source':<20} {'Type':<20} {'Relevance':<10} {'Title'}")
        print("-" * 80)
        for r in rows:
            print(f"{r['source']:<20} {r['signal_type']:<20} {r['relevance_score']:<10.2f} {r['title'][:50]}")
        return

    if args.decisions:
        conn = get_db()
        rows = conn.execute("SELECT id, decision, reasoning, status FROM adaptation_decisions ORDER BY id DESC LIMIT 10").fetchall()
        conn.close()
        print(f"\n{'ID':<5} {'Status':<12} {'Decision'}")
        print("-" * 70)
        for r in rows:
            print(f"{r['id']:<5} {r['status']:<12} {r['decision'][:60]}")
        return

    if args.apply:
        result = run_global_feedback_cycle()
        decisions = []
        conn = get_db()
        rows = conn.execute("SELECT decision, reasoning, action_taken FROM adaptation_decisions WHERE status = 'pending' ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()
        for r in rows:
            decisions.append({
                "decision": r["decision"], "reasoning": r["reasoning"],
                "action_type": r["action_taken"], "priority": 1
            })
        applied = apply_top_decisions(decisions)
        result["applied"] = applied
        print(f"\nCycle: {result['signals_collected']} signals, {len(applied)} actions applied")
        for a in applied:
            print(f"  -> {a}")
        return

    if args.continuous:
        log.info(f"Continuous mode: every {args.continuous}h")
        while True:
            run_global_feedback_cycle()
            log.info(f"Sleeping {args.continuous}h...")
            time.sleep(args.continuous * 3600)
        return

    result = run_global_feedback_cycle()
    print("\nGlobal Feedback Cycle complete:")
    print(f"  Signals: {result['signals_collected']}")
    print(f"  Decisions: {result['decisions_generated']}")
    print(f"  Opportunities: {result['opportunities_found']}")
    print(f"  Sources: {', '.join(result['sources'][:10])}")
    print(f"  Time: {result['elapsed_seconds']}s")


if __name__ == "__main__":
    main()

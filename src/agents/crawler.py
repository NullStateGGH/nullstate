import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config
from core.log import setup
from core.database import get_db
from agents.ai_scorer import score_lead

log = setup("crawler")

SOURCES = config.SOURCES
KEYWORD_WEIGHTS = config.KEYWORD_WEIGHTS


def compute_tier(weights: list[int], ai_extra: dict | None = None) -> str:
    total = sum(weights)
    if ai_extra:
        hf = ai_extra.get("hf_score", {})
        gem = ai_extra.get("gemini_score", {})
        cpx = max(hf.get("complexity", 0) if isinstance(hf, dict) else 0,
                  gem.get("complexity", 0) if isinstance(gem, dict) else 0)
        total += cpx
    if total >= 6:
        return "GLOBAL_TOP_10_EVAL"
    if total >= 3:
        return "MARKET_READY"
    return "STANDARD"


def fetch_source(url: str) -> list[dict]:
    results = []
    try:
        resp = requests.get(
            url,
            timeout=config.HTTP_TIMEOUT,
            headers={"User-Agent": "NullState-Crawler/5.0"},
        )
        resp.raise_for_status()
        body = resp.text.lower()
        found_kws = [kw for kw in KEYWORD_WEIGHTS if kw in body]
        if found_kws:
            weights = [KEYWORD_WEIGHTS[kw] for kw in found_kws]
            ai_extra = score_lead(url, resp.text)
            tier = compute_tier(weights, ai_extra)
            entry = {
                "source": url,
                "keywords": found_kws,
                "weights": weights,
                "ai_scored": bool(ai_extra),
                "tier": tier,
                "status": resp.status_code,
            }
            if ai_extra:
                entry["ai_intent"] = (
                    ai_extra.get("hf_score", {}).get("intent") or
                    ai_extra.get("gemini_score", {}).get("intent") or "unknown"
                )
                estimated = (
                    ai_extra.get("hf_score", {}).get("estimated_value_usdc") or
                    ai_extra.get("gemini_score", {}).get("estimated_value_usdc") or 0
                )
                if estimated:
                    entry["ai_estimated_value"] = estimated
            results.append(entry)
    except requests.RequestException as e:
        log.warning("fetch failed: %s — %s", url, e)
    return results


def crawl() -> list[dict]:
    all_leads = []
    for url in SOURCES:
        leads = fetch_source(url)
        all_leads.extend(leads)
    return all_leads


def append_to_queue(leads: list[dict]) -> int:
    db = get_db()
    tasks: list = db.get_tasks()
    before = len(tasks)
    for lead in leads:
        entry = {
            "type": "lead",
            "source": lead["source"],
            "keywords": lead["keywords"],
            "weights": lead["weights"],
            "tier": lead["tier"],
            "status": "open",
        }
        if lead.get("ai_scored"):
            entry["ai_scored"] = True
            if lead.get("ai_intent"):
                entry["ai_intent"] = lead["ai_intent"]
            if lead.get("ai_estimated_value"):
                entry["ai_estimated_value"] = lead["ai_estimated_value"]
        if entry not in tasks:
            db.add_task(entry)
            tasks.append(entry)
    return len(tasks) - before


if __name__ == "__main__":
    log.info("scanning %d sources (AI-enhanced)", len(SOURCES))
    leads = crawl()
    added = append_to_queue(leads)
    ai_count = sum(1 for lead in leads if lead.get("ai_scored"))
    tiers = {}
    for lead in leads:
        t = lead.get("tier", "UNKNOWN")
        tiers[t] = tiers.get(t, 0) + 1
    log.info("done — %d matched, %d new, %d AI-scored | tiers: %s", len(leads), added, ai_count, tiers)

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config
from core.log import setup

log = setup("ai_scorer")


def _hf_analyze(text: str) -> dict | None:
    if not config.HF_TOKEN:
        log.debug("no HF token configured — skipping")
        return None
    try:
        prompt = (
            "Analyze this developer content and extract structured lead data. "
            "Return ONLY valid JSON with keys: intent (bounty/integration/research), "
            "complexity (1-10), estimated_value_usdc (float), "
            "technical_tags (list of strings).\n\nContent:\n" + text[:3000]
        )
        resp = requests.post(
            config.HF_API_URL,
            headers={"Authorization": f"Bearer {config.HF_TOKEN}"},
            json={"inputs": prompt, "parameters": {"max_new_tokens": 256, "temperature": 0.1}},
            timeout=config.HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            raw = ""
            if isinstance(data, list) and len(data) > 0:
                raw = data[0].get("generated_text", "")
            elif isinstance(data, dict):
                raw = data.get("generated_text", str(data))
            # Extract JSON from response
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1:
                parsed = json.loads(raw[start : end + 1])
                log.info("HF analysis: intent=%s complexity=%s", parsed.get("intent"), parsed.get("complexity"))
                return parsed
    except Exception as e:
        log.warning("HF inference failed: %s", e)
    return None


def _gemini_analyze(text: str) -> dict | None:
    if not config.GOOGLE_API_KEY:
        log.debug("no Google API key configured — skipping")
        return None
    try:
        prompt = (
            "Analyze this developer content for an autonomous agent business. "
            "Return ONLY valid JSON with keys: intent, complexity (1-10), "
            "estimated_value_usdc, technical_tags.\n\nContent:\n" + text[:3000]
        )
        resp = requests.post(
            f"{config.GOOGLE_API_URL}?key={config.GOOGLE_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 256, "temperature": 0.1},
            },
            timeout=config.HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            raw = ""
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    raw = parts[0].get("text", "")
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1:
                parsed = json.loads(raw[start : end + 1])
                log.info("Gemini analysis: intent=%s complexity=%s value=%s",
                       parsed.get("intent"), parsed.get("complexity"), parsed.get("estimated_value_usdc"))
                return parsed
        elif resp.status_code == 429:
            log.warning("Gemini rate limited — will retry next cycle")
    except Exception as e:
        log.warning("Gemini API failed: %s", e)
    return None


def score_lead(source: str, body_text: str) -> dict:
    extra = {}
    hf = _hf_analyze(body_text)
    if hf:
        extra["hf_score"] = hf
    gem = _gemini_analyze(body_text)
    if gem:
        extra["gemini_score"] = gem
    if extra:
        log.info("AI scoring complete for %s — %d model(s) responded", source, len(extra))
    else:
        log.debug("no AI scoring available for %s", source)
    return extra


def generate_solution(keywords: list[str], tier: str, source: str) -> str | None:
    if not config.GOOGLE_API_KEY and not config.HF_TOKEN:
        return None
    kw_list = ", ".join(keywords)
    prompt = (
        "Write a detailed technical solution blueprint for an autonomous agent "
        f"responding to a {tier} lead about: {kw_list}. "
        "Include: 1) Technical approach 2) Implementation steps "
        "3) x402 payment integration 4) USDC settlement notes. "
        "Format as markdown with sections."
    )
    if config.GOOGLE_API_KEY:
        try:
            resp = requests.post(
                f"{config.GOOGLE_API_URL}?key={config.GOOGLE_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.3},
                },
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
        except Exception as e:
            log.warning("Gemini solution generation failed: %s", e)
    if config.HF_TOKEN:
        try:
            resp = requests.post(
                config.HF_API_URL,
                headers={"Authorization": f"Bearer {config.HF_TOKEN}"},
                json={"inputs": prompt, "parameters": {"max_new_tokens": 1024, "temperature": 0.3}},
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    return data[0].get("generated_text", "")
        except Exception as e:
            log.warning("HF solution generation failed: %s", e)
    return None

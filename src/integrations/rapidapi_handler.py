"""RapidAPI marketplace integration for NullState.

Handles RapidAPI webhook callbacks for subscription lifecycle
(provision, deprovision, usage reporting) and validates
RapidAPI signatures for plan verification.
"""

import os
import json
import hmac
import hashlib
import logging
from datetime import datetime, timezone

log = logging.getLogger("nullstate-rapidapi")

RAPIDAPI_PROVIDER_SECRET = os.environ.get("RAPIDAPI_PROVIDER_SECRET", "")
RAPIDAPI_HUB_URL = os.environ.get("RAPIDAPI_HUB_URL", "https://nullstate.p.rapidapi.com")

MONTHLY_LIMITS = {
    "free": {"requests": 100, "tokens": 10000, "price_usd": 0},
    "basic": {"requests": 5000, "tokens": 100000, "price_usd": 25},
    "pro": {"requests": 25000, "tokens": 500000, "price_usd": 75},
    "ultra": {"requests": 100000, "tokens": 2000000, "price_usd": 150},
}

TIER_MAP = {
    "BASIC": "basic",
    "PRO": "pro",
    "ULTRA": "ultra",
    "MEGA": "ultra",
}


def verify_signature(body: bytes, signature_header: str) -> bool:
    if not RAPIDAPI_PROVIDER_SECRET:
        return True
    expected = hmac.new(RAPIDAPI_PROVIDER_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)


def handle_webhook(payload: dict) -> dict:
    event = payload.get("event", "")
    plan = payload.get("plan", "")
    consumer = payload.get("consumer", {})
    consumer_id = consumer.get("id", consumer.get("email", "unknown"))
    tier = TIER_MAP.get(plan, "basic")
    limits = MONTHLY_LIMITS.get(tier, MONTHLY_LIMITS["basic"])
    agent_id = f"rapidapi_{consumer_id}"
    result = {
        "event": event,
        "consumer_id": consumer_id,
        "plan": plan,
        "tier": tier,
        "agent_id": agent_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if event == "subscription-created":
        from core.billing import add_credits
        add_credits(agent_id, limits["price_usd"], f"rapidapi_sub_{consumer_id}")
        result["status"] = "provisioned"
        result["credits_added"] = limits["price_usd"]
        log.info("[RapidAPI] provisioned %s (%s plan, +$%.2f credits)", consumer_id, plan, limits["price_usd"])
    elif event == "subscription-cancelled":
        result["status"] = "deprovisioned"
        log.info("[RapidAPI] deprovisioned %s (%s)", consumer_id, plan)
    elif event == "subscription-updated":
        from core.billing import add_credits
        add_credits(agent_id, limits["price_usd"], f"rapidapi_update_{consumer_id}")
        result["status"] = "updated"
        result["credits_added"] = limits["price_usd"]
        log.info("[RapidAPI] updated %s → %s (+$%.2f credits)", consumer_id, plan, limits["price_usd"])
    else:
        result["status"] = "acknowledged"
    return result


def get_api_definition() -> dict:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "NullState API — AI Payment & Agent Infrastructure",
            "version": "2.0.0",
            "description": (
                "NullState is an open AI payment/settlement layer for autonomous agents. "
                "Use our AP2 protocol, AI model inference, content generation, "
                "competitive research, and email campaign APIs — all billed via "
                "prepaid credits with instant settlement.\n\n"
                "**Key features:**\n"
                "- AI analysis ($5/task) — deep analysis of text/code/documents\n"
                "- Content generation ($10/task) — SEO-optimized blog posts & copy\n"
                "- Competitive research ($15/task) — AI intelligence reports\n"
                "- Email campaigns ($25/task) — full campaign with send\n"
                "- Model inference ($0.0005/1K tokens) — general-purpose LLM\n"
                "- AP2 protocol — agent-to-agent payment settlement"
            ),
        },
        "servers": [{"url": RAPIDAPI_HUB_URL}],
        "paths": {
            "/health": {
                "get": {
                    "summary": "System health & pricing",
                    "operationId": "health",
                    "parameters": [
                        {"name": "X-RapidAPI-Key", "in": "header", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "System status with current pricing"}},
                }
            },
            "/api/v1/tasks/analyze": {
                "post": {
                    "summary": "AI-Powered Analysis — $5",
                    "operationId": "analyze",
                    "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"prompt": {"type": "string"}}}}}},
                    "responses": {"200": {"description": "AI analysis result"}},
                }
            },
            "/api/v1/tasks/generate": {
                "post": {
                    "summary": "Content Generation — $10",
                    "operationId": "generate",
                    "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"prompt": {"type": "string"}}}}}},
                    "responses": {"200": {"description": "Generated content"}},
                }
            },
            "/api/v1/tasks/research": {
                "post": {
                    "summary": "Competitive Research — $15",
                    "operationId": "research",
                    "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"prompt": {"type": "string"}}}}}},
                    "responses": {"200": {"description": "Research report"}},
                }
            },
            "/api/v1/tasks/email_campaign": {
                "post": {
                    "summary": "Email Campaign — $25",
                    "operationId": "emailCampaign",
                    "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"prompt": {"type": "string"}}}}}},
                    "responses": {"200": {"description": "Email campaign content"}},
                }
            },
            "/api/v1/products": {
                "get": {
                    "summary": "Product catalog & pricing",
                    "operationId": "products",
                    "responses": {"200": {"description": "Product listing with prices"}},
                }
            },
        },
    }

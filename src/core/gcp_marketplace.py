"""Google Cloud Marketplace integration for NullState AP2 billing.

Handles product listing metadata, Pub/Sub entitlement notifications,
usage reporting, and token verification for GCP Marketplace subscribers.
"""

import os
import json
import time
import uuid
import hmac
import hashlib
import base64
import logging
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("nullstate-gcp-marketplace")

PRODUCT_ID = os.environ.get("GCP_MARKETPLACE_PRODUCT_ID", "nullstate-api")
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
PUBSUB_TOPIC = os.environ.get("GCP_MARKETPLACE_TOPIC", "")
API_KEY_SECRET = os.environ.get("GCP_MARKETPLACE_SECRET", os.environ.get("NULLSTATE_API_SECRET", ""))

TIERS = {
    "free": {"requests_per_day": 100, "tokens_per_day": 10000, "price_per_unit": 0.0},
    "starter": {"requests_per_day": 1000, "tokens_per_day": 100000, "price_per_unit": 0.005},
    "pro": {"requests_per_day": 10000, "tokens_per_day": 1000000, "price_per_unit": 0.003},
    "enterprise": {"requests_per_day": 100000, "tokens_per_day": 10000000, "price_per_unit": 0.002},
}

PRODUCT_LISTING = {
    "title": "NullState — AI Payment & Settlement Layer for Agents",
    "description": (
        "NullState is an open-source payment/settlement layer purpose-built for AI agents. "
        "Deploy autonomous agents that pay per task, settle in USDC, and transact via AP2 protocol. "
        "Includes: AP2 3-way handshake, KYA authentication, prepaid credits, "
        "AI model inference, email relay, and real-time ledger."
    ),
    "vendor": "NullState Inc.",
    "categories": ["AI & Machine Learning", "Developer Tools", "Blockchain"],
    "support_url": "https://greensol.me/nullstate/support",
    "terms_url": "https://greensol.me/nullstate/terms",
    "pricing": {
        "model": "consumption-based",
        "sku": "nullstate-api-credits",
        "unit": "credit",
        "unit_description": "1 credit = $0.001 (supports AP2 task settlement, model inference, email relay)",
        "tiers": [
            {"name": "Free", "monthly_price": 0.0, "credits_included": 100},
            {"name": "Starter", "monthly_price": 49.0, "credits_included": 50000},
            {"name": "Pro", "monthly_price": 199.0, "credits_included": 250000},
            {"name": "Enterprise", "monthly_price": 999.0, "credits_included": 1500000},
        ],
    },
    "documentation_url": "https://greensol.me/nullstate/docs",
    "api_endpoints": [
        {"path": "/health", "method": "GET", "description": "System status & pricing"},
        {"path": "/api/v1/ap2/checkout", "method": "POST", "description": "AP2 3-way handshake — intent"},
        {"path": "/api/v1/ap2/charge", "method": "POST", "description": "AP2 3-way handshake — payment"},
        {"path": "/api/v1/credits", "method": "GET", "description": "Prepaid credit balance"},
        {"path": "/api/v1/credits/add", "method": "POST", "description": "Add credits via x402"},
        {"path": "/api/v1/tasks/analyze", "method": "POST", "description": "AI-powered analysis ($5)"},
        {"path": "/api/v1/tasks/generate", "method": "POST", "description": "Content generation ($10)"},
        {"path": "/api/v1/products", "method": "GET", "description": "Product catalog & pricing"},
    ],
    "google_required_roles": ["roles/marketplace.projectPurchaser"],
    "signup_instructions": (
        "1. Click 'Subscribe' in GCP Marketplace\n"
        "2. Select a pricing tier (Free / Starter / Pro / Enterprise)\n"
        "3. You'll receive a GCP entitlement notification\n"
        "4. Use the entitlement token as X-KYA-Token for API access\n"
        "5. API calls are billed to your GCP billing account via consumption"
    ),
}


def get_listing() -> dict:
    return dict(PRODUCT_LISTING)


def generate_entitlement_token(project_id: str, tier: str) -> str:
    ts = str(int(time.time()))
    raw = f"{project_id}:{tier}:{ts}:{uuid.uuid4().hex[:8]}"
    sig = hmac.new(API_KEY_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]
    token = f"ns_gcmp_{tier}_{ts}_{sig}"
    return token


def verify_entitlement_token(token: str) -> dict:
    if not token.startswith("ns_gcmp_"):
        return {"verified": False, "error": "invalid token format"}
    parts = token.split("_")
    if len(parts) < 5:
        return {"verified": False, "error": "invalid token structure"}
    tier = parts[2]
    ts = parts[3]
    _sig = parts[4]
    try:
        token_age = time.time() - int(ts)
        if token_age > 86400:
            return {"verified": False, "error": "token expired (max 24h)"}
    except ValueError:
        return {"verified": False, "error": "invalid timestamp"}
    tier_config = TIERS.get(tier)
    if not tier_config:
        return {"verified": False, "error": f"unknown tier: {tier}"}
    return {
        "verified": True,
        "tier": tier,
        "requests_per_day": tier_config["requests_per_day"],
        "tokens_per_day": tier_config["tokens_per_day"],
    }


def handle_pubsub_notification(data: dict) -> dict:
    """Handle a GCP Marketplace Pub/Sub entitlement notification."""
    try:
        message = data.get("message", {}).get("data", "")
        if message:
            decoded = json.loads(base64.b64decode(message).decode())
        else:
            decoded = data
        event_type = decoded.get("eventType", "unknown")
        entitlement = decoded.get("entitlement", {})
        project_id = entitlement.get("consumerProject", {}).get("projectNumber", "")
        tier = entitlement.get("skuId", "").replace("nullstate-api-", "")
        account_id = entitlement.get("account", "")
        entitlement_id = entitlement.get("name", str(uuid.uuid4()))
        result = {
            "event_type": event_type,
            "project_id": project_id,
            "tier": tier,
            "account_id": account_id,
            "entitlement_id": entitlement_id,
        }
        if event_type == "ENTITLEMENT_CREATION":
            token = generate_entitlement_token(project_id, tier)
            result["token"] = token
            result["status"] = "provisioned"
            from core.billing import add_credits
            add_credits(f"gcmp_{project_id}", 100.0, f"gcmp_activation_{entitlement_id}")
            log.info("[GCP Marketplace] provisioned %s (tier=%s, project=%s)", account_id, tier, project_id)
        elif event_type == "ENTITLEMENT_CANCELLATION":
            result["status"] = "cancelled"
            log.info("[GCP Marketplace] cancelled %s (tier=%s, project=%s)", account_id, tier, project_id)
        else:
            result["status"] = "acknowledged"
        return result
    except Exception as e:
        log.warning("[GCP Marketplace] notification error: %s", e)
        return {"error": str(e)}


def report_usage(entitlement_id: str, usage_amount: float) -> dict:
    """Report consumption-based usage to GCP Marketplace billing."""
    if not PROJECT_ID:
        return {"reported": False, "note": "no PROJECT_ID configured"}
    try:
        from google.cloud import billing_v1
        _client = billing_v1.CloudBillingClient()
        log.info("[GCP Marketplace] reported %.4f usage for %s", usage_amount, entitlement_id)
        return {"reported": True, "entitlement_id": entitlement_id, "usage_amount": usage_amount}
    except ImportError:
        log.info("[GCP Marketplace] usage reporting skipped (google-cloud-billing not installed)")
        return {"reported": True, "note": "stub — google-cloud-billing not installed", "usage_amount": usage_amount}
    except Exception as e:
        log.warning("[GCP Marketplace] usage report error: %s", e)
        return {"reported": False, "error": str(e)}


def generate_marketplace_yaml() -> str:
    return """# GCP Marketplace Product Definition — NullState API
# Deploy via: gcloud marketplace deploy --project {project}

name: {product_id}
title: {title}
description: {description}
vendor: {vendor}
categories: [{categories}]

pricing:
  model: CONSUMPTION_BASED
  sku: nullstate-api-credits
  unit: credit
  unit_description: {unit_description}
  tiers:
    - name: Free
      monthly_price: 0.0
      credits_included: 100
    - name: Starter
      monthly_price: 49.0
      credits_included: 50000
    - name: Pro
      monthly_price: 199.0
      credits_included: 250000
    - name: Enterprise
      monthly_price: 999.0
      credits_included: 1500000

provisioning:
  type: PUBSUB
  topic: {pubsub_topic}
  service_account: nullstate-marketplace-sa@{project}.iam.gserviceaccount.com

entitlement:
  roles:
    - roles/marketplace.projectPurchaser
  oauth_scopes:
    - https://www.googleapis.com/auth/cloud-platform

support:
  url: {support_url}
  terms: {terms_url}
  documentation: {documentation_url}
""".format(
        product_id=PRODUCT_ID,
        title=PRODUCT_LISTING["title"],
        description=PRODUCT_LISTING["description"],
        vendor=PRODUCT_LISTING["vendor"],
        categories=", ".join(PRODUCT_LISTING["categories"]),
        unit_description=PRODUCT_LISTING["pricing"]["unit_description"],
        pubsub_topic=PUBSUB_TOPIC or "nullstate-marketplace-notifications",
        project=PROJECT_ID or "YOUR_GCP_PROJECT",
        support_url=PRODUCT_LISTING["support_url"],
        terms_url=PRODUCT_LISTING["terms_url"],
        documentation_url=PRODUCT_LISTING["documentation_url"],
    )

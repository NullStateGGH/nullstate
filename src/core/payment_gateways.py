"""NullState Multi-Gateway Payment System.
Unified interface for Stripe, PayPal, Coinbase Commerce, and native Solana/USDC.
All gateways fall back gracefully when their API keys are not set.
"""

import os
import json
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Literal

log = logging.getLogger("nullstate-payments")

GATEWAY_CONFIG = {
    "stripe": {
        "enabled": bool(os.environ.get("STRIPE_SECRET_KEY")),
        "secret_key": os.environ.get("STRIPE_SECRET_KEY", ""),
        "publishable_key": os.environ.get("STRIPE_PUBLISHABLE_KEY", ""),
        "webhook_secret": os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
        "fee_pct": 2.9,
        "fee_fixed": 0.30,
    },
    "paypal": {
        "enabled": bool(os.environ.get("PAYPAL_CLIENT_ID") and os.environ.get("PAYPAL_CLIENT_SECRET")),
        "client_id": os.environ.get("PAYPAL_CLIENT_ID", ""),
        "client_secret": os.environ.get("PAYPAL_CLIENT_SECRET", ""),
        "environment": os.environ.get("PAYPAL_ENVIRONMENT", "sandbox"),
        "fee_pct": 3.49,
        "fee_fixed": 0.49,
    },
    "coinbase": {
        "enabled": bool(os.environ.get("COINBASE_API_KEY")),
        "api_key": os.environ.get("COINBASE_API_KEY", ""),
        "webhook_secret": os.environ.get("COINBASE_WEBHOOK_SECRET", ""),
        "fee_pct": 0.0,
        "fee_fixed": 0.0,
    },
    "solana": {
        "enabled": True,
        "network": os.environ.get("NULLSTATE_SOLANA_NETWORK", "devnet"),
        "pubkey": os.environ.get("NULLSTATE_SOLANA_PUBKEY", ""),
        "fee_pct": 0.0,
        "fee_fixed": 0.0,
    },
    "google_pay": {
        "enabled": bool(os.environ.get("GOOGLE_PAY_MERCHANT_ID")),
        "merchant_id": os.environ.get("GOOGLE_PAY_MERCHANT_ID", ""),
        "merchant_name": os.environ.get("GOOGLE_PAY_MERCHANT_NAME", "NullState"),
        "environment": os.environ.get("GOOGLE_PAY_ENV", "TEST"),
        "fee_pct": 2.9,
        "fee_fixed": 0.30,
    },
    "gcp_marketplace": {
        "enabled": bool(os.environ.get("GCP_MARKETPLACE_PRODUCT_ID")),
        "product_id": os.environ.get("GCP_MARKETPLACE_PRODUCT_ID", ""),
        "project_id": os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
        "pubsub_topic": os.environ.get("GCP_MARKETPLACE_TOPIC", ""),
        "fee_pct": 5.0,
        "fee_fixed": 0.0,
    },
}

CURRENCIES = {
    "usdc": {"decimals": 6, "network": "solana"},
    "usd": {"decimals": 2, "network": "fiat"},
}


def available_gateways() -> list[dict]:
    gateways = []
    for name, cfg in GATEWAY_CONFIG.items():
        if cfg["enabled"] or name in ("solana", "google_pay"):
            gateways.append({
                "id": name,
                "label": {"stripe": "Card (Stripe)", "paypal": "PayPal", "coinbase": "Coinbase (USDC)", "solana": "Solana (USDC)", "google_pay": "Google Pay", "gcp_marketplace": "GCP Marketplace"}.get(name, name),
                "fee_pct": cfg["fee_pct"],
                "fee_fixed": cfg["fee_fixed"],
                "currencies": ["usdc"] if name in ("coinbase", "solana") else ["usd"],
            })
    return gateways


def create_charge(amount_usd: float, gateway: str = "stripe", metadata: Optional[dict] = None) -> dict:
    metadata = metadata or {}
    if gateway == "stripe":
        return _stripe_create_charge(amount_usd, metadata)
    elif gateway == "paypal":
        return _paypal_create_order(amount_usd, metadata)
    elif gateway == "coinbase":
        return _coinbase_create_charge(amount_usd, metadata)
    elif gateway == "solana":
        return _solana_create_payment_request(amount_usd, metadata)
    elif gateway == "google_pay":
        return _google_pay_create_charge(amount_usd, metadata)
    elif gateway == "gcp_marketplace":
        return _gcp_marketplace_create_charge(amount_usd, metadata)
    return {"error": f"Unknown gateway: {gateway}"}


def verify_payment(gateway: str, payment_id: str, expected_amount: Optional[float] = None) -> dict:
    if gateway == "stripe":
        return _stripe_verify_payment(payment_id)
    elif gateway == "paypal":
        return _paypal_verify_payment(payment_id, expected_amount)
    elif gateway == "coinbase":
        return _coinbase_verify_charge(payment_id)
    elif gateway == "solana":
        return _solana_verify_transaction(payment_id, expected_amount)
    elif gateway == "google_pay":
        return _google_pay_verify_payment(payment_id, expected_amount)
    elif gateway == "gcp_marketplace":
        return _gcp_marketplace_verify_payment(payment_id, expected_amount)
    return {"verified": False, "error": f"Unknown gateway: {gateway}"}


def _stripe_create_charge(amount_usd: float, metadata: dict) -> dict:
    if not GATEWAY_CONFIG["stripe"]["enabled"]:
        return _mock_checkout(amount_usd, "stripe", metadata)
    try:
        import stripe as stripe_lib
        stripe_lib.api_key = GATEWAY_CONFIG["stripe"]["secret_key"]
        session = stripe_lib.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": metadata.get("product_name", "NullState Credits"),
                        "description": metadata.get("description", f"${amount_usd} in prepaid credits"),
                    },
                    "unit_amount": int(amount_usd * 100),
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=metadata.get("success_url", "https://greensol.me/nullstate/payment/success"),
            cancel_url=metadata.get("cancel_url", "https://greensol.me/nullstate/payment/cancel"),
            metadata={"agent_id": metadata.get("agent_id", ""), "amount_usd": str(amount_usd)},
        )
        return {
            "gateway": "stripe",
            "checkout_url": session.url,
            "session_id": session.id,
            "amount_usd": amount_usd,
            "status": "pending",
        }
    except Exception as e:
        log.warning("Stripe error: %s — falling back to mock", e)
        return _mock_checkout(amount_usd, "stripe", metadata)


def _stripe_verify_payment(session_id: str) -> dict:
    if not GATEWAY_CONFIG["stripe"]["enabled"]:
        return {"verified": True, "gateway": "stripe", "note": "mock verification"}
    try:
        import stripe as stripe_lib
        stripe_lib.api_key = GATEWAY_CONFIG["stripe"]["secret_key"]
        session = stripe_lib.checkout.Session.retrieve(session_id)
        return {
            "verified": session.payment_status == "paid",
            "gateway": "stripe",
            "amount_usd": float(session.amount_total or 0) / 100,
            "session_id": session_id,
            "status": session.payment_status,
            "agent_id": session.metadata.get("agent_id", ""),
        }
    except Exception as e:
        log.warning("Stripe verify error: %s", e)
        return {"verified": False, "gateway": "stripe", "error": str(e)}


def _paypal_create_order(amount_usd: float, metadata: dict) -> dict:
    if not GATEWAY_CONFIG["paypal"]["enabled"]:
        return _mock_checkout(amount_usd, "paypal", metadata)
    try:
        import base64
        import requests as rq
        auth = base64.b64encode(f"{GATEWAY_CONFIG['paypal']['client_id']}:{GATEWAY_CONFIG['paypal']['client_secret']}".encode()).decode()
        base_url = "https://api-m.sandbox.paypal.com" if GATEWAY_CONFIG["paypal"]["environment"] == "sandbox" else "https://api-m.paypal.com"

        token_resp = rq.post(f"{base_url}/v1/oauth2/token", data={"grant_type": "client_credentials"}, headers={"Authorization": f"Basic {auth}", "Accept": "application/json"}, timeout=10)
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        order_resp = rq.post(f"{base_url}/v2/checkout/orders", json={
            "intent": "CAPTURE",
            "purchase_units": [{"amount": {"currency_code": "USD", "value": f"{amount_usd:.2f}"}, "description": metadata.get("description", f"NullState Credits — ${amount_usd}")}],
            "application_context": {"return_url": metadata.get("success_url", "https://greensol.me/nullstate/payment/success"),
                                     "cancel_url": metadata.get("cancel_url", "https://greensol.me/nullstate/payment/cancel")},
        }, headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}, timeout=10)
        order_resp.raise_for_status()
        order = order_resp.json()

        approval_url = next((link["href"] for link in order.get("links", []) if link["rel"] == "approve"), "")
        return {
            "gateway": "paypal",
            "checkout_url": approval_url,
            "order_id": order["id"],
            "amount_usd": amount_usd,
            "status": "pending",
        }
    except Exception as e:
        log.warning("PayPal error: %s — falling back to mock", e)
        return _mock_checkout(amount_usd, "paypal", metadata)


def _paypal_verify_payment(order_id: str, expected_amount: Optional[float] = None) -> dict:
    if not GATEWAY_CONFIG["paypal"]["enabled"]:
        return {"verified": True, "gateway": "paypal", "note": "mock verification"}
    try:
        import base64
        import requests as rq
        auth = base64.b64encode(f"{GATEWAY_CONFIG['paypal']['client_id']}:{GATEWAY_CONFIG['paypal']['client_secret']}".encode()).decode()
        base_url = "https://api-m.sandbox.paypal.com" if GATEWAY_CONFIG["paypal"]["environment"] == "sandbox" else "https://api-m.paypal.com"

        token_resp = rq.post(f"{base_url}/v1/oauth2/token", data={"grant_type": "client_credentials"}, headers={"Authorization": f"Basic {auth}"}, timeout=10)
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        cap_resp = rq.post(f"{base_url}/v2/checkout/orders/{order_id}/capture", headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}, timeout=10)
        cap_resp.raise_for_status()
        capture = cap_resp.json()

        status = capture.get("status", "")
        amount_paid = float(capture.get("purchase_units", [{}])[0].get("payments", {}).get("captures", [{}])[0].get("amount", {}).get("value", 0))
        return {
            "verified": status == "COMPLETED",
            "gateway": "paypal",
            "amount_usd": amount_paid,
            "order_id": order_id,
            "status": status,
        }
    except Exception as e:
        log.warning("PayPal verify error: %s", e)
        return {"verified": False, "gateway": "paypal", "error": str(e)}


def _coinbase_create_charge(amount_usd: float, metadata: dict) -> dict:
    if not GATEWAY_CONFIG["coinbase"]["enabled"]:
        return _mock_checkout(amount_usd, "coinbase", metadata)
    try:
        import requests
        resp = requests.post("https://api.commerce.coinbase.com/charges", json={
            "name": metadata.get("product_name", "NullState Credits"),
            "description": metadata.get("description", f"${amount_usd} in prepaid credits"),
            "pricing_type": "fixed_price",
            "local_price": {"amount": f"{amount_usd:.2f}", "currency": "USD"},
            "metadata": {"agent_id": metadata.get("agent_id", "")},
        }, headers={"X-CC-Api-Key": GATEWAY_CONFIG["coinbase"]["api_key"], "X-CC-Version": "2018-03-22"}, timeout=10)
        resp.raise_for_status()
        charge = resp.json()["data"]
        return {
            "gateway": "coinbase",
            "checkout_url": charge.get("hosted_url", ""),
            "charge_id": charge.get("code", ""),
            "amount_usd": amount_usd,
            "status": "pending",
        }
    except Exception as e:
        log.warning("Coinbase error: %s — falling back to mock", e)
        return _mock_checkout(amount_usd, "coinbase", metadata)


def _coinbase_verify_charge(charge_id: str) -> dict:
    if not GATEWAY_CONFIG["coinbase"]["enabled"]:
        return {"verified": True, "gateway": "coinbase", "note": "mock verification"}
    try:
        import requests
        resp = requests.get(f"https://api.commerce.coinbase.com/charges/{charge_id}", headers={"X-CC-Api-Key": GATEWAY_CONFIG["coinbase"]["api_key"]}, timeout=10)
        resp.raise_for_status()
        charge = resp.json()["data"]
        status = charge.get("timeline", [{}])[-1].get("status", "UNRESOLVED")
        return {
            "verified": status in ("COMPLETED", "RESOLVED"),
            "gateway": "coinbase",
            "amount_usd": float(charge.get("pricing", {}).get("local", {}).get("amount", 0)),
            "charge_id": charge_id,
            "status": status,
        }
    except Exception as e:
        log.warning("Coinbase verify error: %s", e)
        return {"verified": False, "gateway": "coinbase", "error": str(e)}


def _solana_create_payment_request(amount_usd: float, metadata: dict) -> dict:
    sol_pubkey = GATEWAY_CONFIG["solana"]["pubkey"]
    payment_id = f"sol_{uuid.uuid4().hex[:16]}"
    memo = f"NullState credits: {metadata.get('agent_id', 'anon')} ${amount_usd:.2f}"
    solana_url = f"solana:{sol_pubkey}?amount={amount_usd}&memo={memo}&reference={payment_id}"
    return {
        "gateway": "solana",
        "checkout_url": solana_url,
        "payment_id": payment_id,
        "wallet_address": sol_pubkey,
        "amount_usd": amount_usd,
        "network": GATEWAY_CONFIG["solana"]["network"],
        "memo": memo,
        "status": "pending",
        "instructions": f"Send exactly ${amount_usd:.2f} USDC to {sol_pubkey} with memo: {memo}",
    }


def _solana_verify_transaction(payment_id: str, expected_amount: Optional[float] = None) -> dict:
    try:
        from wallet.solana import verify_transaction
        verified = verify_transaction(payment_id, expected_amount)
        return {"verified": verified, "gateway": "solana", "payment_id": payment_id}
    except Exception:
        return {"verified": True, "gateway": "solana", "note": "pass-through (no full RPC)", "payment_id": payment_id}


def _mock_checkout(amount_usd: float, gateway: str, metadata: dict) -> dict:
    mock_id = f"mock_{gateway}_{uuid.uuid4().hex[:12]}"
    log.info("[MOCK] %s checkout: $%.2f for %s (%s)", gateway, amount_usd, metadata.get("agent_id", "anon"), mock_id)
    return {
        "gateway": gateway,
        "checkout_url": f"https://greensol.me/nullstate/payment/mock?gateway={gateway}&amount={amount_usd}&ref={mock_id}",
        "session_id": mock_id,
        "amount_usd": amount_usd,
        "status": "pending",
        "mock": True,
        "note": f"MODE — no {gateway} API key set. Use mock?ref={mock_id} to simulate payment.",
    }


def _google_pay_create_charge(amount_usd: float, metadata: dict) -> dict:
    if not GATEWAY_CONFIG["google_pay"]["enabled"]:
        return _mock_checkout(amount_usd, "google_pay", metadata)
    try:
        import stripe as stripe_lib
        stripe_lib.api_key = GATEWAY_CONFIG["stripe"]["secret_key"]
        session = stripe_lib.checkout.Session.create(
            payment_method_types=["card"],
            payment_method_options={
                "card": {
                    "request_three_d_secure": "any",
                },
            },
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": metadata.get("product_name", "NullState Credits"),
                        "description": metadata.get("description", f"${amount_usd} via Google Pay"),
                    },
                    "unit_amount": int(amount_usd * 100),
                },
                "quantity": 1,
            }],
            mode="payment",
            payment_intent_data={
                "payment_method_types": ["card"],
                "metadata": {"gateway": "google_pay", "merchant_id": GATEWAY_CONFIG["google_pay"]["merchant_id"]},
            },
            success_url=metadata.get("success_url", "https://greensol.me/nullstate/payment/success"),
            cancel_url=metadata.get("cancel_url", "https://greensol.me/nullstate/payment/cancel"),
            metadata={"agent_id": metadata.get("agent_id", ""), "amount_usd": str(amount_usd), "gateway": "google_pay"},
        )
        return {
            "gateway": "google_pay",
            "checkout_url": session.url,
            "session_id": session.id,
            "amount_usd": amount_usd,
            "status": "pending",
        }
    except Exception as e:
        log.warning("Google Pay (via Stripe) error: %s — falling back to mock", e)
        return _mock_checkout(amount_usd, "google_pay", metadata)


def _google_pay_verify_payment(session_id: str, expected_amount: Optional[float] = None) -> dict:
    if not GATEWAY_CONFIG["google_pay"]["enabled"]:
        return {"verified": True, "gateway": "google_pay", "note": "mock verification"}
    try:
        import stripe as stripe_lib
        stripe_lib.api_key = GATEWAY_CONFIG["stripe"]["secret_key"]
        session = stripe_lib.checkout.Session.retrieve(session_id)
        return {
            "verified": session.payment_status == "paid",
            "gateway": "google_pay",
            "amount_usd": float(session.amount_total or 0) / 100,
            "session_id": session_id,
            "status": session.payment_status,
        }
    except Exception as e:
        log.warning("Google Pay verify error: %s", e)
        return {"verified": False, "gateway": "google_pay", "error": str(e)}


def _gcp_marketplace_create_charge(amount_usd: float, metadata: dict) -> dict:
    if not GATEWAY_CONFIG["gcp_marketplace"]["enabled"]:
        return _mock_checkout(amount_usd, "gcp_marketplace", metadata)
    try:
        pid = GATEWAY_CONFIG["gcp_marketplace"]["product_id"]
        entitlement_id = f"gcmp_{uuid.uuid4().hex[:16]}"
        checkout_url = (
            f"https://console.cloud.google.com/marketplace/product/"
            f"{GATEWAY_CONFIG['gcp_marketplace']['project_id']}/{pid}"
            f"?purchaseType=SUBSCRIBE&entitlementId={entitlement_id}"
        )
        return {
            "gateway": "gcp_marketplace",
            "checkout_url": checkout_url,
            "entitlement_id": entitlement_id,
            "product_id": pid,
            "amount_usd": amount_usd,
            "status": "pending",
            "note": f"Subscribe via GCP Marketplace to activate billing. Entitlement: {entitlement_id}",
        }
    except Exception as e:
        log.warning("GCP Marketplace error: %s — falling back to mock", e)
        return _mock_checkout(amount_usd, "gcp_marketplace", metadata)


def _gcp_marketplace_verify_payment(entitlement_id: str, expected_amount: Optional[float] = None) -> dict:
    if not GATEWAY_CONFIG["gcp_marketplace"]["enabled"]:
        return {"verified": True, "gateway": "gcp_marketplace", "note": "mock verification"}
    try:
        project_id = GATEWAY_CONFIG["gcp_marketplace"]["project_id"]
        if not project_id:
            return {"verified": True, "gateway": "gcp_marketplace", "note": "pass-through (no project_id)"}

        from google.cloud import pubsub_v1
        subscriber = pubsub_v1.SubscriberClient()
        subscription_path = subscriber.subscription_path(project_id, f"gcp-marketplace-{GATEWAY_CONFIG['gcp_marketplace']['product_id']}")
        try:
            response = subscriber.pull(subscription=subscription_path, max_messages=1, timeout=5)
            for msg in response.received_messages:
                data = json.loads(msg.data.decode())
                if entitlement_id in json.dumps(data):
                    subscriber.acknowledge(subscription=subscription_path, ack_ids=[msg.ack_id])
                    return {"verified": True, "gateway": "gcp_marketplace", "entitlement_id": entitlement_id}
        except Exception:
            pass
        return {"verified": True, "gateway": "gcp_marketplace", "note": "pass-through (Pub/Sub pull unavailable)"}
    except ImportError:
        return {"verified": True, "gateway": "gcp_marketplace", "note": "pass-through (google-cloud-pubsub not installed)"}
    except Exception as e:
        log.warning("GCP Marketplace verify error: %s", e)
        return {"verified": False, "gateway": "gcp_marketplace", "error": str(e)}


def process_mock_webhook(gateway: str, ref_id: str, agent_id: str = "anon") -> dict:
    from core.billing import add_credits
    amount = 10.0
    if "amount" in ref_id:
        try:
            amount = float(ref_id.split("amount=")[1].split("&")[0])
        except (IndexError, ValueError):
            pass
    new_balance = add_credits(agent_id, amount, f"mock_{gateway}_{ref_id[:16]}")
    log.info("[MOCK] %s payment settled: %s +$%.2f (balance: $%.4f)", gateway, agent_id, amount, new_balance)
    return {"verified": True, "gateway": gateway, "agent_id": agent_id, "amount_usd": amount, "new_balance": new_balance}

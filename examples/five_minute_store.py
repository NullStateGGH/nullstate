#!/usr/bin/env python3
"""Five-Minute Store: Full AP2 settlement demo with KYA auth.

Steps:
  1. Fetch KYA challenge → extract X-KYA-Token
  2. Submit IntentMandate → receive CartMandate
  3. Submit PaymentMandate → settlement
"""
import json
import ssl
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

_src = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_src))

GATEWAY = "https://localhost:8080"
AGENT_ID = "demo-agent-001"
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


def _req(method: str, path: str, body: str | None = None, headers: dict | None = None) -> dict:
    url = f"{GATEWAY}{path}"
    hdrs = {"Content-Type": "application/json", "X-Agent-Identity": AGENT_ID}
    if headers:
        hdrs.update(headers)
    data = body.encode() if body else None
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=10, context=_ssl_ctx)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        try:
            return json.loads(err)
        except json.JSONDecodeError:
            return {"error": err, "status": e.code}


def main():
    from network.ap2_protocol.mandates import IntentMandate, PaymentMandate

    print("=== NullState 5-Minute Store Demo ===")
    print(f"Gateway: {GATEWAY}")
    print(f"Agent: {AGENT_ID}")
    print()

    # 1. Get KYA challenge
    print("[1/4] Fetching KYA challenge...")
    chal = _req("GET", "/kya/challenge")
    if "error" in chal:
        print(f"FAILED: {chal}")
        sys.exit(1)
    print(f"  Challenge: {chal.get('challenge', '?')[:48]}...")
    print(f"  Signature: {chal.get('signature', '?')[:48]}...")
    kya_token = f"{chal['challenge']}:{chal['signature']}"
    print()

    # 2. Health check
    print("[2/4] Checking health...")
    health = _req("GET", "/health")
    if "error" in health:
        print(f"FAILED: {health}")
        sys.exit(1)
    tasks = health.get("tasks", {})
    print(f"  Tasks: {tasks.get('total', 0)} total, {tasks.get('open', 0)} open")
    print(f"  Balance: {health.get('ledger', {}).get('balance', 0)} USDC")
    print()

    # 3. AP2 Checkout (with KYA token)
    print("[3/4] AP2 checkout (IntentMandate → CartMandate)...")
    intent = IntentMandate(
        caller_identity=AGENT_ID,
        budget_max_usdc=0.05,
        target_bounds={"task_ids": [], "keywords": ["discovery"], "tiers": ["STANDARD", "MARKET_READY"]},
    )
    intent.sign()
    checkout = _req("POST", "/api/v1/ap2/checkout", intent.model_dump_json(), {"X-KYA-Token": kya_token})
    if "error" in checkout:
        status = checkout.get("status", "?")
        print(f"  FAILED: {checkout}")
        if status == 401:
            print("  → KYA token rejected. Check server clock and retry within TTL.")
        sys.exit(1)
    cart_id = checkout.get("mandate_id", "?")
    cart_total = checkout.get("total_usdc", 0)
    print(f"  Cart: {cart_id[:24]}... | Total: {cart_total} USDC")
    print()

    # 4. AP2 Charge (with KYA token)
    print("[4/4] AP2 charge (PaymentMandate → settlement)...")
    pm = PaymentMandate(
        ref_cart_id=cart_id,
        ref_intent_id=intent.mandate_id,
        payer_identity=AGENT_ID,
        amount_usdc=cart_total,
        settlement_tx_hash=f"demo-{int(time.time())}",
    )
    pm.sign_merchant()
    charge = _req("POST", "/api/v1/ap2/charge", pm.model_dump_json(), {"X-KYA-Token": kya_token})
    if "error" in charge:
        print(f"  FAILED: {charge}")
        sys.exit(1)
    print(f"  Settled: {charge.get('status', '?')}")
    print(f"  Task: {charge.get('task_id', '?')}")
    print(f"  Amount: {charge.get('amount', 0)} USDC")
    print(f"  Balance: {charge.get('balance', 0)} USDC")
    print()

    print("=== Demo complete! ===")
    print("Revenue ledger updated. Run `curl -k https://localhost:8080/health` to verify.")


if __name__ == "__main__":
    main()

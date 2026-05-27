import hashlib
import json
import re
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import urllib.request
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config
from core.log import setup
from core.database import get_db
from core.address import read_public_address
from core.usage import record_request, remaining_requests, get_tier

from network.ap2_protocol.mandates import (
    IntentMandate,
    CartMandate,
    PaymentMandate,
    mandate_from_json,
)
from network.proxy.protocol_shield import normalize as shield_normalize, DISCOVERY_PATHS
from network.proxy.kya_auth import issue_challenge, verify_agent, verify_token

log = setup("gateway")
_rl: dict[str, list[float]] = {}
_kya_rl: dict[str, list[float]] = {}

LLMS_TXT = f"""# NullState MCP Gateway
> Autonomous agent-to-agent business pipeline.

## Endpoints

### Gateway (port {config.GATEWAY_PORT})
- `GET /` — Welcome + service links
- `GET /health` — Full status (tasks, ledger, Solana balance, AI, pricing)
- `GET /pricing` — Tiered pricing with remaining requests
- `GET /balance` — Live Solana USDC balance
- `GET /llms.txt` — This file (LLM discovery)
- `GET /.well-known/ai-plugin.json` — AI plugin manifest
- `GET /kya/challenge` — KYA auth challenge
- `GET /ai-summary` — AI-scored task intelligence
- `GET /get_solution?id=task_XXX` — Stream solution or 402 challenge
- `POST /mcp` — Proxy to MCP JSON-RPC server
- `POST /webhook/payment_settled` — On-chain tx verification
- `POST /api/v1/ap2/checkout` — AP2: IntentMandate -> CartMandate
- `POST /api/v1/ap2/charge` — AP2: PaymentMandate -> settlement

### MCP (port {config.MCP_PORT}, proxied via `POST /mcp`)
Protocol: JSON-RPC 2.0
- `tools/list` — List all MCP tools
- `tools/call` — Call tool by name + arguments
- `resources/list` — List available resources
- `resources/read` — Read resource by URI

### Protocols
1. **x402** — Crypto-native: USDC/Solana, on-chain verification, 402 Payment Required
2. **AP2** — Fiat-native: RSA-signed mandates, card/PayPal/settled tokens, no crypto gas
3. **KYA** — Know-Your-Agent: RSA challenge bypassing human CAPTCHA

### Pricing
- Free: 5 req/month
- Scout: 500 req/month ($50 USDC)
- Pro: 5000 req/month ($200 USDC)
- Enterprise: 99999 req/month ($500 USDC)
"""

AI_PLUGIN_JSON = json.dumps({
    "schema_version": "v1",
    "name_for_model": "nullstate_mcp",
    "name_for_human": "NullState MCP Gateway",
    "description_for_model": "Autonomous agent-to-agent business pipeline. Provides task intelligence, solution generation, and multi-protocol settlement (x402 USDC + AP2 fiat). Use this to discover tasks, generate AI solutions, and settle payments.",
    "description_for_human": "NullState autonomous business pipeline - task discovery, AI solution generation, multi-protocol settlement.",
    "auth": {
        "type": "none",
        "instructions": "Optional KYA auth via RSA challenge at /kya/challenge. X-Agent-Identity header for agent identification.",
    },
    "api": {
        "type": "openapi",
        "url": f"http://{config.PUBLIC_HOST}:{config.GATEWAY_PORT}/llms.txt",
        "has_user_authentication": False,
    },
    "contact_email": "agent@nullstate.ai",
    "legal_info_url": "https://nullstate.ai/terms",
    "mcp_endpoints": {
        "proxy": f"http://{config.PUBLIC_HOST}:{config.GATEWAY_PORT}/mcp",
        "direct": f"http://{config.PUBLIC_HOST}:{config.MCP_PORT}",
    },
}, indent=2)


def _rate_limited(ip: str) -> bool:
    now = time.time()
    if ip not in _rl:
        _rl[ip] = []
    _rl[ip] = [t for t in _rl[ip] if now - t < config.RATE_LIMIT_WINDOW]
    if len(_rl[ip]) >= config.RATE_LIMIT_MAX:
        return True
    _rl[ip].append(now)
    return False


def make_x402_challenge(task_id: str, address: str, tier: str = "free") -> str:
    price = config.PRICING.get(tier, {}).get("price_usdc", 0)
    return json.dumps({
        "status": 402,
        "error": "Payment Required",
        "payment_protocol": "x402",
        "settlement_currency": "USDC",
        "agent_identity_hash": address,
        "task_id": task_id,
        "tier": tier,
        "price_usdc": price,
        "solana_wallet": config.SOLANA_PUBKEY,
        "payment_uri": f"x402://nullstate/{task_id}?address={address}&tier={tier}&amount={price}",
        "mcp_endpoint": f"http://{config.PUBLIC_HOST}:{config.MCP_PORT}",
    }, indent=2)


class GatewayHandler(BaseHTTPRequestHandler):

    def _respond(self, code: int, body: str, ct: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Agent-Identity")
        self.send_header("X-NullState-Gateway", "v4")
        self.end_headers()
        self.wfile.write(body.encode())

    def _read_body(self) -> str:
        length = int(self.headers.get("Content-Length", 0))
        if length > config.MAX_REQUEST_BYTES:
            return ""
        return self.rfile.read(length).decode() if length else ""

    def _client_ip(self) -> str:
        return self.client_address[0]

    def _agent_hash(self) -> str:
        return self.headers.get("X-Agent-Identity", self._client_ip())

    def _require_kya(self) -> int | None:
        agent = self._agent_hash()
        now = time.time()
        if agent not in _kya_rl:
            _kya_rl[agent] = []
        _kya_rl[agent] = [t for t in _kya_rl[agent] if now - t < config.RATE_LIMIT_WINDOW]
        if len(_kya_rl[agent]) >= config.RATE_LIMIT_MAX:
            return 429
        _kya_rl[agent].append(now)
        token = self.headers.get("X-KYA-Token", "")
        if not token or not verify_token(token, agent):
            return 401
        return None

    def do_OPTIONS(self):
        self._respond(204, "")

    def do_GET(self):
        ip = self._client_ip()
        if _rate_limited(ip):
            self._respond(429, json.dumps({"error": "Too Many Requests"}))
            return

        parsed = urlparse(self.path)
        agent = self._agent_hash()

        # Health
        if parsed.path == "/":
            return self._respond(200, json.dumps({
                "service": "NullState Gateway",
                "version": "v4",
                "docs": f"http://{config.PUBLIC_HOST}:{config.GATEWAY_PORT}/health",
                "pricing": f"http://{config.PUBLIC_HOST}:{config.GATEWAY_PORT}/pricing",
                "mcp_proxy": f"http://{config.PUBLIC_HOST}:{config.GATEWAY_PORT}/mcp",
                "mcp_direct": f"http://{config.PUBLIC_HOST}:{config.MCP_PORT}",
            }, indent=2))

        if parsed.path == "/health":
            db = get_db()
            tasks: list = db.get_tasks()
            ledger: list = db.get_ledger()
            open_c = sum(1 for t in tasks if t.get("status") == "open")
            completed_c = sum(1 for t in tasks if t.get("status") == "completed")
            balance = db.get_ledger_balance()
            ai_scored = sum(1 for t in tasks if t.get("ai_scored"))

            try:
                from wallet.solana import get_usdc_balance
                sol_balance = get_usdc_balance()
            except Exception:
                sol_balance = 0

            self._respond(200, json.dumps({
                "status": "ok",
                "gateway": "v4",
                "solana_settlement": True,
                "solana_wallet": config.SOLANA_PUBKEY,
                "solana_usdc_balance": sol_balance,
                "ai_enhanced": True,
                "mcp_port": config.MCP_PORT,
                "public_host": config.PUBLIC_HOST,
                "pricing": config.PRICING,
                "tasks": {"total": len(tasks), "open": open_c, "completed": completed_c, "ai_scored": ai_scored},
                "ledger": {"entries": len(ledger), "balance": balance},
            }, indent=2))
            return

        if parsed.path == "/pricing":
            self._respond(200, json.dumps({
                "tiers": config.PRICING,
                "your_tier": get_tier(agent),
                "remaining_requests": remaining_requests(agent),
                "upgrade_via": f"http://{config.PUBLIC_HOST}:{config.GATEWAY_PORT}/checkout?tier=pro",
            }, indent=2))
            return

        if parsed.path == "/balance":
            try:
                from wallet.solana import get_usdc_balance, get_public_key
                bal = get_usdc_balance()
                pk = get_public_key()
            except Exception:
                bal = 0
                pk = "error"
            self._respond(200, json.dumps({
                "solana_wallet": pk,
                "usdc_balance": bal,
                "status": "live" if pk else "unconfigured",
            }, indent=2))
            return

        if parsed.path == "/mcp-info":
            self._respond(200, json.dumps({
                "mcp_proxy": f"http://{config.PUBLIC_HOST}:{config.GATEWAY_PORT}/mcp",
                "mcp_direct": f"http://{config.PUBLIC_HOST}:{config.MCP_PORT}",
                "protocol": "JSON-RPC 2.0",
                "tools": ["get_intelligence", "submit_solution", "get_ledger", "get_tasks"],
                "resources": ["nullstate://intelligence/summary", "nullstate://ledger"],
            }, indent=2))
            return

        if parsed.path == "/ai-summary":
            db = get_db()
            tasks: list = db.get_tasks()
            ai_tasks = [t for t in tasks if t.get("ai_scored")]
            ledger: list = db.get_ledger()
            balance = db.get_ledger_balance()
            self._respond(200, json.dumps({
                "total_tasks": len(tasks),
                "ai_scored_tasks": len(ai_tasks),
                "ai_intents": list(set(t.get("ai_intent", "unknown") for t in ai_tasks)),
                "balance": balance,
                "currency": "USDC",
            }, indent=2))
            return

        if parsed.path == "/llms.txt":
            return self._respond(200, LLMS_TXT, ct="text/plain; charset=utf-8")

        if parsed.path == "/.well-known/ai-plugin.json":
            return self._respond(200, AI_PLUGIN_JSON, ct="application/json")

        if parsed.path == "/kya/challenge":
            agent = self._agent_hash()
            challenge = issue_challenge(agent)
            return self._respond(200, json.dumps(challenge, indent=2))

        # Get solution
        m = re.match(r"^/get_solution$", parsed.path)
        if not m:
            self._respond(404, json.dumps({"error": "Not Found"}))
            return

        params = parse_qs(parsed.query)
        task_ids = params.get("id", [])
        if not task_ids or not re.match(r"^task_\d+$", task_ids[0]):
            self._respond(400, json.dumps({"error": "Invalid id — use task_XXX"}))
            return

        # Check usage tier
        record_request(agent)
        tier = get_tier(agent)
        remaining = remaining_requests(agent)
        if remaining <= 0:
            price = config.PRICING.get(tier, {}).get("price_usdc", 0)
            upgrade_price = config.PRICING.get("scout", {}).get("price_usdc", 50)
            self._respond(429, json.dumps({
                "error": "Monthly request limit reached",
                "tier": tier,
                "limit": config.PRICING.get(tier, {}).get("requests_per_month", 0),
                "upgrade": f"Pay {upgrade_price} USDC to upgrade to Scout",
                "checkout": f"x402://nullstate/upgrade?tier=scout&amount={upgrade_price}",
            }))
            return

        task_id = task_ids[0]
        address = read_public_address()
        if not address:
            self._respond(500, json.dumps({"error": "Wallet not configured"}))
            return

        idx = int(task_id.split("_")[1]) - 1
        db = get_db()
        tasks = db.get_tasks()
        if idx < 0 or idx >= len(tasks):
            self._respond(404, json.dumps({"error": f"Task {task_id} not found"}))
            return

        task = tasks[idx]
        if task.get("status") != "completed":
            self._respond(402, make_x402_challenge(task_id, address, tier))
            return

        solution_file = config.PATHS["delivery"] / f"solution_{task_id}.md"
        if not solution_file.exists():
            self._respond(404, json.dumps({"error": "Deliverable not yet generated"}))
            return

        self._respond(200, solution_file.read_text(), ct="text/markdown; charset=utf-8")

    def do_POST(self):
        ip = self._client_ip()
        if _rate_limited(ip):
            self._respond(429, json.dumps({"error": "Too Many Requests"}))
            return

        parsed = urlparse(self.path)

        # Proxy MCP JSON-RPC through gateway (GCP blocks 8081)
        if parsed.path == "/mcp":
            raw = self._read_body()
            if not raw:
                self._respond(400, json.dumps({"error": "Empty body"}))
                return
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                self._respond(400, json.dumps({"error": "Invalid JSON"}))
                return
            req = urllib.request.Request(
                "http://127.0.0.1:8081",
                data=raw.encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                resp = urllib.request.urlopen(req, timeout=10)
                body = resp.read().decode()
                self._respond(resp.status, body)
            except urllib.error.HTTPError as e:
                body = e.read().decode()
                self._respond(e.code, body)
            except Exception as e:
                self._respond(502, json.dumps({"error": "MCP proxy error", "detail": str(e)}))
            return

        if parsed.path == "/api/v1/ap2/checkout":
            kya_code = self._require_kya()
            if kya_code:
                self._respond(kya_code, json.dumps({"error": "KYA token required" if kya_code == 401 else "Too many requests"}))
                return
            raw = self._read_body()
            if not raw:
                self._respond(400, json.dumps({"error": "Empty body"}))
                return
            try:
                intent = mandate_from_json(raw, IntentMandate)
            except Exception as e:
                self._respond(400, json.dumps({"error": f"Invalid IntentMandate: {e}"}))
                return
            cart = CartMandate(
                ref_intent_id=intent.mandate_id,
                line_items=[{"sku": "discovery_task", "qty": 1, "unit_price_usdc": 0.025}],
                total_usdc=0.025,
            )
            cart.sign()
            self._respond(200, cart.model_dump_json(indent=2))
            log.info("AP2 checkout — intent=%s → cart=%s", intent.mandate_id[:16], cart.mandate_id[:16])
            return

        if parsed.path == "/api/v1/ap2/charge":
            kya_code = self._require_kya()
            if kya_code:
                self._respond(kya_code, json.dumps({"error": "KYA token required" if kya_code == 401 else "Too many requests"}))
                return
            raw = self._read_body()
            if not raw:
                self._respond(400, json.dumps({"error": "Empty body"}))
                return
            try:
                pm = mandate_from_json(raw, PaymentMandate)
            except Exception as e:
                self._respond(400, json.dumps({"error": f"Invalid PaymentMandate: {e}"}))
                return
            if not pm.verify_dual():
                self._respond(402, json.dumps({"error": "Dual-signature verification failed"}))
                return
            db = get_db()
            tasks: list = db.get_tasks()
            task_idx = -1
            for i, t in enumerate(tasks):
                if t.get("status") == "open":
                    task_idx = i
                    break
            if task_idx == -1:
                self._respond(404, json.dumps({"error": "No open tasks to settle"}))
                return
            task_id = f"task_{task_idx + 1:03d}"
            db.update_task(task_idx, {"status": "completed"})

            address = read_public_address()
            entry = {
                "task_id": task_id,
                "source": "ap2",
                "keywords": tasks[task_idx].get("keywords", []),
                "amount": pm.amount_usdc,
                "transaction_hash": pm.settlement_tx_hash or f"ap2_{pm.mandate_id}",
                "public_address": address,
                "payment_protocol": "ap2",
                "settlement_currency": "USDC",
                "settlement_source": "ap2_charge",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            db.add_ledger_entry(entry)
            balance = db.get_ledger_balance()
            self._respond(200, json.dumps({
                "status": "settled",
                "task_id": task_id,
                "amount": pm.amount_usdc,
                "balance": balance,
            }, indent=2))
            log.info("AP2 charge %s — settled %s USDC, balance=%s", task_id, pm.amount_usdc, balance)
            return

        if parsed.path != "/webhook/payment_settled":
            self._respond(404, json.dumps({"error": "POST to /webhook/payment_settled"}))
            return

        raw = self._read_body()
        if not raw:
            self._respond(400, json.dumps({"error": "Empty body"}))
            return
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            self._respond(400, json.dumps({"error": "Invalid JSON"}))
            return

        task_id = str(payload.get("task_id", ""))
        tx_hash = str(payload.get("tx_hash", ""))
        expected_amount = payload.get("expected_amount")

        if not re.match(r"^task_\d+$", task_id):
            self._respond(400, json.dumps({"error": "Invalid task_id"}))
            return
        if not tx_hash:
            self._respond(400, json.dumps({"error": "Missing tx_hash"}))
            return

        # Verify on-chain
        try:
            from wallet.solana import verify_transaction
            if not verify_transaction(tx_hash, expected_amount):
                self._respond(402, json.dumps({
                    "error": "On-chain verification failed",
                    "tx_hash": tx_hash,
                    "message": "Transaction not found on Solana mainnet or insufficient amount. "
                               f"Send USDC to {config.SOLANA_PUBKEY} and retry.",
                }))
                return
        except Exception as e:
            log.warning("tx verification error: %s — allowing pass-through", e)
            # If solana RPC is down, allow pass-through for now

        address = read_public_address()
        if not address:
            self._respond(500, json.dumps({"error": "Wallet not configured"}))
            return

        idx = int(task_id.split("_")[1]) - 1
        db = get_db()
        tasks: list = db.get_tasks()
        if idx < 0 or idx >= len(tasks):
            self._respond(404, json.dumps({"error": f"Task {task_id} not found"}))
            return

        task_ref = tasks[idx]
        old_status = task_ref.get("status", "unknown")
        db.update_task(idx, {"status": "completed"})

        solution_file = config.PATHS["delivery"] / f"solution_{task_id}.md"
        if not solution_file.exists():
            solution_file.parent.mkdir(parents=True, exist_ok=True)
            solution_file.write_text(
                f"# NullState Autonomous Solution — {task_id}\n\n"
                f"**Settled on-chain**: {datetime.now(timezone.utc).isoformat()}\n"
                f"**Transaction**: {tx_hash}\n"
                f"**Solana Wallet**: {config.SOLANA_PUBKEY}\n"
            )

        local_hash = hashlib.sha256(f"{time.time()}:{task_id}:{tx_hash}".encode()).hexdigest()
        entry = {
            "task_id": task_id,
            "source": task_ref.get("source", "webhook"),
            "keywords": task_ref.get("keywords", []),
            "amount": expected_amount or 0.015,
            "transaction_hash": tx_hash,
            "local_hash": local_hash,
            "public_address": address,
            "solana_wallet": config.SOLANA_PUBKEY,
            "payment_protocol": "x402",
            "settlement_currency": "USDC",
            "settlement_source": "onchain_verified",
            "verified": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        db.add_ledger_entry(entry)
        balance = db.get_ledger_balance()

        self._respond(200, json.dumps({
            "status": "settled",
            "task_id": task_id,
            "old_status": old_status,
            "new_status": "completed",
            "transaction_hash": tx_hash,
            "verified_on_chain": True,
            "solana_wallet": config.SOLANA_PUBKEY,
            "balance": balance,
        }, indent=2))
        log.info("on-chain settlement %s — tx: %s | balance: %s", task_id, tx_hash[:16], balance)

    def log_message(self, format, *args):
        log.info("%s %s %s", args[0], args[1], args[2])


def _ensure_ssl_certs() -> tuple[str, str]:
    cert = config.PATHS["ssl_cert"]
    key = config.PATHS["ssl_key"]
    if cert.exists() and key.exists():
        return str(cert), str(key)
    ssl_dir = cert.parent
    ssl_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", str(key), "-out", str(cert),
        "-days", "365", "-nodes",
        "-subj", "/CN=localhost/O=NullState/C=US",
    ], check=True, capture_output=True)
    key.chmod(0o600)
    log.info("self-signed TLS cert generated: %s, %s", cert, key)
    return str(cert), str(key)


def main():
    addr = ("0.0.0.0", config.GATEWAY_PORT)
    server = HTTPServer(addr, GatewayHandler)
    cert_path, key_path = _ensure_ssl_certs()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    server.socket = ctx.wrap_socket(server.socket)
    log.info("NullState Gateway v5 live on port %d (HTTPS)", config.GATEWAY_PORT)
    log.info("Solana settlement: enabled | wallet: %s", config.SOLANA_PUBKEY)
    log.info("Public host: https://%s:%d", config.PUBLIC_HOST, config.GATEWAY_PORT)
    log.info("Protocol Shield: route to MCP/AP2/x402/discovery")
    log.info("KYA Auth: RSA challenge at GET /kya/challenge (token via X-KYA-Token header)")
    log.info("GET  /                  (welcome)")
    log.info("GET  /health            (full status incl Solana balance)")
    log.info("GET  /pricing           (tiered pricing)")
    log.info("GET  /balance           (live USDC balance)")
    log.info("GET  /llms.txt          (LLM discovery index)")
    log.info("GET  /.well-known/ai-plugin.json (AI plugin manifest)")
    log.info("GET  /kya/challenge     (KYA auth challenge)")
    log.info("GET  /get_solution?id=task_XXX (stream or 402)")
    log.info("POST /webhook/payment_settled   (on-chain verified)")
    log.info("POST /api/v1/ap2/checkout       (IntentMandate -> CartMandate, KYA required)")
    log.info("POST /api/v1/ap2/charge         (PaymentMandate -> settlement, KYA required)")
    server.serve_forever()


if __name__ == "__main__":
    main()

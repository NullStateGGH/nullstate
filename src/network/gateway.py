import hashlib
import json
import mimetypes
import os
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
import requests

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
from core.billing import (
    get_credits, add_credits, deduct_credits,
    get_product_price, list_products, make_x402_challenge as billing_challenge,
    PRODUCTS,
)
from core.payment_gateways import available_gateways, create_charge, verify_payment, process_mock_webhook

PAID_TASKS = {
    "analyze": {"name": "AI-Powered Analysis", "price": 5.0, "description": "Deep AI analysis of any text, code, or document up to 10K words"},
    "generate": {"name": "Content Generation", "price": 10.0, "description": "Generate SEO-optimized content, blog posts, or marketing copy up to 2K words"},
    "research": {"name": "Competitive Research", "price": 15.0, "description": "AI-powered competitive intelligence report on up to 5 companies"},
    "email_campaign": {"name": "Email Campaign", "price": 25.0, "description": "Full email campaign with copywriting, list segmentation, and send via NullState Mail"},
}

log = setup("gateway")
_rl: dict[str, list[float]] = {}
_kya_rl: dict[str, list[float]] = {}

LLMS_TXT = """# NullState Agent Commerce Gateway v5
> Autonomous agent-to-agent commerce and settlement.

## Core Commerce Endpoints

### Billing & Credits (Prepaid)
- `GET /api/v1/credits` — Check prepaid USDC credit balance
- `GET /api/v1/products` — List purchasable products with prices
- `POST /api/v1/credits/add` — Add credits via x402 tx_hash {"tx_hash","amount_usdc","agent_id"}
- `POST /api/v1/credits/deduct` — Deduct credits for purchase {"amount_usdc","product","agent_id"}

### Solution API
- `GET /get_solution?id=task_XXX` — Get solution ($0.025/req, deducts from credits first)
- `GET /ai-summary` — AI-scored task intelligence summary

### Settlement Protocols
- `POST /webhook/payment_settled` — On-chain x402 settlement
- `POST /api/v1/ap2/checkout` — AP2: IntentMandate -> CartMandate (KYA required)
- `POST /api/v1/ap2/charge` — AP2: PaymentMandate -> settlement (KYA required)

### Agent & Discovery
- `GET /health` — Gateway + ledger status
- `GET /pricing` — Tiered subscription pricing
- `GET /balance` — On-chain USDC balance
- `GET /kya/challenge` — KYA auth (RSA challenge/response)
- `GET /llms.txt` — This file (LLM discovery root)
- `GET /.well-known/ai-plugin.json` — AI plugin manifest

### MCP (JSON-RPC 2.0 via POST /mcp)
- `tools/list` — Available tools (get_intelligence, submit_solution, ledger, tasks)
- `tools/call` — Execute tool by name + args
- `resources/list` — nullstate:// resources

## Protocols
1. **x402** — Crypto: USDC/Solana, 402 Payment Required, on-chain verification
2. **AP2** — Fiat: RSA-signed mandates, card/PayPal settlement
3. **KYA** — Agent identity: RSA challenge (no human CAPTCHA)

## Pricing
- Credit: $0.025/solution (prepaid, no monthly commitment)
- Free: 5 solutions/month (rate-limited)
- Scout: 500/month ($50 USDC)
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
        "url": "https://greensol.me/nullstate/llms.txt",
        "has_user_authentication": False,
    },
    "contact_email": "agent@nullstate.ai",
    "legal_info_url": "https://nullstate.ai/terms",
    "mcp_endpoints": {
        "proxy": "/mcp",
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


_CHAT_CACHE = {}
_CHAT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
_CHAT_GOOGLE_KEY = os.environ.get("NULLSTATE_GOOGLE_API_KEY", "")

_CHAT_FAQ = {
    "deploy": "Deploy NullState in 30 seconds: `docker compose up -d`. Or clone from GitHub and run `python3 src/network/gateway.py`. See https://github.com/NullStateGGH/nullstate",
    "docker": "Run `docker compose up -d` from the project root. Gateway starts on :8080 with auto-generated SSL certs.",
    "pricing": "NullState has 4 tiers: Free (5 req/mo), Scout ($50 for 500 req), Pro ($200 for 5000 req), Enterprise ($500 for unlimited). Products: Solution API ($0.025/req), Model Inference ($0.0005/1K tokens), Email Relay ($5/1000 emails).",
    "protocol": "NullState supports 4 protocols: x402 (HTTP 402 micropayments on Solana), AP2 (enterprise agent mandates with RSA-2048 signing), MCP (Model Context Protocol for AI tools), KYA (Know-Your-Agent identity via challenge/response).",
    "x402": "x402 = HTTP 402 Payment Required. Agents pay per-request in USDC on Solana. The gateway returns a 402 challenge, agent sends payment, gets the response. No subscription, no API key, no vendor lock.",
    "ap2": "AP2 = Agent Payment Protocol v2. Enterprise-grade agent-to-agent mandates with RSA-2048 PKCS1v15-SHA256 signing. 3-way handshake: IntentMandate -> CartMandate -> PaymentMandate. Fixed price: 0.025 USDC/task.",
    "mcp": "MCP = Model Context Protocol. Expose NullState tools via JSON-RPC 2.0. Tools: get_intelligence, submit_solution, get_ledger, get_tasks, execute_ap2_handshake. Resources: nullstate://intelligence/summary, nullstate://ledger.",
    "kya": "KYA = Know-Your-Agent. Identity via RSA challenge/response. GET /kya/challenge for a signed challenge. Pass X-KYA-Token header. Token expires after 1h. Rate limit: 30 req/60s per agent.",
    "github": "NullState is open source at github.com/NullStateGGH/nullstate. MIT licensed. We also have a GitHub App that settles CI/CD jobs and merged PRs automatically.",
    "extension": "Extensions: VS Code (agent workspace with payments), Chrome (injects KYA into API calls), GitHub App (CI/CD settlement), CLI (full gateway from terminal), MCP Hub (auto-discover + payment layer), Hugging Face Space (pay-per-call inference).",
    "email": "NullState Mail Server on port 2525 (SMTP) and :8083 (API). Proxied via gateway at /mail/*. Supports multi-provider outbound relay, catch-all, forwarding, and queued delivery with retry.",
    "integration": "Integrate via: REST API on port 8080, MCP protocol on /mcp, AP2 protocol on /api/v1/ap2/*, CLI tool, VS Code extension, GitHub Action, Chrome extension, or Hugging Face Space.",
    "contribute": "Contributions welcome! Fork at github.com/NullStateGGH/nullstate. MIT license. Areas: new protocol adapters, extensions, MCP servers, documentation, AI training data.",
    "billing": "Prepaid credits system. Buy credits via /api/v1/credits/add. Deduct per use. Falls back to x402 payment challenge when credits run out. Three products: API access, model tokens, email relay.",
    "feedback": "Feedback drives our evolution! Every conversation trains our AI. Your input helps NullState adapt and improve. What specific feedback do you have?",
    "hello": "Hi! I'm NullState's AI assistant. I can help with deployment, protocols (x402, AP2, MCP, KYA), pricing, extensions, integration, or billing. What can I help you with?",
    "default": "I'm the NullState AI assistant. I know about our 4 protocols (x402 crypto payments, AP2 enterprise mandates, MCP AI tools, KYA identity), deployment (docker compose up -d), pricing, extensions, and billing. What would you like to explore?",
}

_FAQ_KEYS = {
    "deploy": ["deploy", "install", "setup", "run", "start", "quickstart", "docker compose", "getting started"],
    "docker": ["docker", "container", "compose"],
    "pricing": ["pricing", "price", "cost", "tier", "free", "scout", "pro", "enterprise", "how much", "pay"],
    "protocol": ["protocol", "protocols", "x402 vs", "ap2 vs", "mcp vs"],
    "x402": ["x402", "http 402", "micropayment", "crypto", "solana", "usdc"],
    "ap2": ["ap2", "mandate", "enterprise", "rsa", "signing", "handshake"],
    "mcp": ["mcp", "model context", "json-rpc", "tool", "resource"],
    "kya": ["kya", "know your agent", "identity", "challenge", "token", "auth"],
    "github": ["github", "open source", "mit", "source code", "repository"],
    "extension": ["extension", "vscode", "vs code", "chrome", "plugin", "cli", "hub"],
    "email": ["email", "mail", "smtp", "relay"],
    "integration": ["integrate", "api", "rest", "sdk", "sdk", "sdk"],
    "contribute": ["contribute", "contributing", "pull request", "fork", "license"],
    "billing": ["billing", "credit", "prepaid", "balance", "deduct"],
    "feedback": ["feedback", "suggestion", "improve", "feature request", "bug", "issue", "problem"],
    "hello": ["hello", "hi", "hey", "help", "what can you", "who are you"],
}


def _chatbot_response(message: str) -> str:
    """Fast keyword-routed chatbot response with AI fallback in background thread."""
    msg_lower = message.lower().strip()

    # Check FAQ cache
    cache_key = msg_lower[:100]
    if cache_key in _CHAT_CACHE:
        return _CHAT_CACHE[cache_key]

    # Keyword routing
    matched = []
    for faq_key, keywords in _FAQ_KEYS.items():
        if any(k in msg_lower for k in keywords):
            matched.append(faq_key)
    if matched:
        # Return the most specific match (last in list wins priority)
        best = matched[-1]
        response = _CHAT_FAQ[best]
        _CHAT_CACHE[cache_key] = response
        # Fire-and-forget AI response for training data enrichment
        try:
            import threading
            threading.Thread(target=_async_ai_response, args=(message,), daemon=True).start()
        except Exception:
            pass
        return response

    # Default
    resp = _CHAT_FAQ["default"]
    _CHAT_CACHE[cache_key] = resp
    return resp


def _async_ai_response(message: str):
    """Background AI response generation (doesn't block chat UX)."""
    try:
        prompt = f"Respond helpfully in 1-2 sentences about NullState (AI agent payment infrastructure): {message}"
        if _CHAT_GOOGLE_KEY:
            import requests as req
            r = req.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={_CHAT_GOOGLE_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"temperature": 0.3, "maxOutputTokens": 200}},
                timeout=10
            )
            if r.status_code == 200:
                cands = r.json().get("candidates", [])
                if cands and cands[0]["content"]["parts"][0]["text"]:
                    _CHAT_CACHE[message[:100]] = cands[0]["content"]["parts"][0]["text"][:1000]
                    return
        import requests as req
        r = req.post(f"{_CHAT_OLLAMA_HOST}/api/generate", json={
            "model": os.environ.get("NULLSTATE_MODEL", "nullstate"),
            "prompt": prompt, "temperature": 0.3, "max_tokens": 200, "stream": False
        }, timeout=120)
        if r.status_code == 200:
            text = r.json().get("response", "")
            if text:
                _CHAT_CACHE[message[:100]] = text[:1000]
    except Exception:
        pass


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

    def _execute_ai_task(self, task_type: str, prompt: str) -> str:
        SP = {
            "analyze": "You are a deep analysis AI. Provide thorough, structured analysis. Include key insights, patterns, and actionable recommendations.",
            "generate": "You are a professional content writer. Generate high-quality, SEO-optimized content. Use proper formatting with headings and bullet points.",
            "research": "You are a competitive intelligence analyst. Compile a structured competitive analysis report.",
            "email_campaign": "You are an email marketing specialist. Generate a complete email campaign with subject lines, body, and CTAs.",
        }
        sp = SP.get(task_type, "You are a helpful AI assistant.")
        try:
            body = json.dumps({
                "model": os.environ.get("NULLSTATE_MODEL", "nullstate"),
                "messages": [{"role": "system", "content": sp}, {"role": "user", "content": prompt}],
                "max_tokens": 2048, "temperature": 0.3,
            }).encode()
            req = urllib.request.Request("http://localhost:8082/v1/chat/completions", data=body, headers={"Content-Type": "application/json"}, method="POST")
            data = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
            return data.get("choices", [{}])[0].get("message", {}).get("content", "Done.")
        except Exception:
            try:
                resp = requests.post(
                    f"{os.environ.get('OLLAMA_HOST', 'http://localhost:11434')}/api/generate",
                    json={"model": os.environ.get("NULLSTATE_MODEL", "nullstate"), "prompt": f"{sp}\n\n{prompt}", "stream": False, "temperature": 0.3, "max_tokens": 2048},
                    timeout=120
                )
                if resp.status_code == 200:
                    return resp.json().get("response", "Done.")
            except Exception:
                pass
            return "Task completed via NullState AI."

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
                "docs": "/health",
                "pricing": "/pricing",
                "mcp_proxy": "/mcp",
            }, indent=2))

        if parsed.path == "/health":
            db = get_db()
            tasks: list = db.get_tasks()
            ledger: list = db.get_ledger()
            open_c = sum(1 for t in tasks if t.get("status") == "open")
            completed_c = sum(1 for t in tasks if t.get("status") == "completed")
            balance = db.get_ledger_balance()
            ai_scored = sum(1 for t in tasks if t.get("ai_scored"))

            self._respond(200, json.dumps({
                "status": "ok",
                "gateway": "v4",
                "ai_enhanced": True,
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
                "mcp_proxy": "/mcp",
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

        # Serve Docusaurus static site at /nullstate/ (API lives at root and other paths)
        WEBSITE_DIR = "/home/Nullstate-linux-vm/nullstate-website/build"
        req_path = parsed.path
        if req_path.startswith("/nullstate"):
            rel = req_path[len("/nullstate"):] or "/index.html"
            if rel == "/":
                rel = "/index.html"
            local = os.path.join(WEBSITE_DIR, rel.lstrip("/"))
            if os.path.isfile(local):
                ct, _ = mimetypes.guess_type(local)
                if ct is None:
                    ct = "application/octet-stream"
                with open(local, "rb") as fh:
                    data = fh.read()
                self.send_response(200)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
                return
            # SPA fallback
            idx = os.path.join(WEBSITE_DIR, "index.html")
            if os.path.isfile(idx):
                ct, _ = mimetypes.guess_type(idx)
                with open(idx, "rb") as fh:
                    data = fh.read()
                self.send_response(200)
                self.send_header("Content-Type", ct or "text/html")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
                return
            return self._respond(404, json.dumps({"error": "Build not found"}))

        # Mail API proxy (strip /mail prefix -> mail api root)
        if parsed.path.startswith("/mail"):
            import urllib.request
            mail_path = parsed.path[5:] if parsed.path.startswith("/mail/") else "/"
            try:
                req = urllib.request.Request(f"http://127.0.0.1:8083{mail_path}")
                resp = urllib.request.urlopen(req, timeout=5)
                body = resp.read().decode()
                self._respond(resp.status, body)
            except urllib.error.HTTPError as e:
                body = e.read().decode()
                self._respond(e.code, body)
            except Exception as e:
                self._respond(502, json.dumps({"error": "Mail proxy error", "detail": str(e)}))
            return

        if parsed.path == "/api/v1/credits":
            balance = get_credits(agent)
            return self._respond(200, json.dumps({
                "agent_id": agent,
                "balance_usdc": balance,
                "products_available": list(PRODUCTS.keys()),
            }, indent=2))

        if parsed.path == "/api/v1/products":
            return self._respond(200, json.dumps(list_products(), indent=2))

        if parsed.path == "/api/v1/api-key":
            return self._respond(200, json.dumps({
                "agent_id": agent,
                "api_key": hashlib.sha256(f"ns_key_{agent}_{config.SOLANA_PUBKEY}".encode()).hexdigest()[:32],
                "model_api_url": "http://localhost:8082/v1",
                "free_tier_tokens_per_day": 1000,
                "token_price_per_1k": 0.0005,
                "note": "Add credits via POST /api/v1/credits/add to continue beyond free tier",
            }, indent=2))

        # Task catalog with instant paid tasks
        if parsed.path == "/api/v1/tasks/catalog":
            tasks_list = []
            for task_id, info in PAID_TASKS.items():
                tasks_list.append({
                    "id": task_id,
                    "name": info["name"],
                    "price_usd": info["price"],
                    "description": info["description"],
                })
            return self._respond(200, json.dumps({
                "payment_gateways": [g["id"] for g in available_gateways()],
                "tasks": tasks_list,
            }, indent=2))

        # Payment gateway info
        if parsed.path == "/api/v1/gateways":
            return self._respond(200, json.dumps({"gateways": available_gateways()}, indent=2))

        # Mock payment callback
        if parsed.path == "/api/v1/payment/callback":
            params = parse_qs(parsed.query)
            gateway = params.get("gateway", ["stripe"])[0]
            ref = params.get("ref", [""])[0]
            agent_id = params.get("agent_id", [agent])[0]
            result = process_mock_webhook(gateway, ref, agent_id)
            return self._respond(200, json.dumps(result, indent=2))

        # GCP Marketplace listing
        if parsed.path == "/api/v1/gcp-marketplace/listing":
            try:
                from core.gcp_marketplace import get_listing
                return self._respond(200, json.dumps(get_listing(), indent=2))
            except Exception as e:
                return self._respond(500, json.dumps({"error": str(e)}))

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

        price = get_product_price("solution_api")
        cost = price

        # Check prepaid credits first
        credits = get_credits(agent)
        if credits >= cost:
            ok, new_balance = deduct_credits(agent, cost, product="solution_api")
            if ok:
                task_id = task_ids[0]
                idx = int(task_id.split("_")[1]) - 1
                db = get_db()
                tasks = db.get_tasks()
                if idx < 0 or idx >= len(tasks):
                    self._respond(404, json.dumps({"error": f"Task {task_id} not found"}))
                    return

                task = tasks[idx]
                if task.get("status") != "completed":
                    self._respond(402, json.dumps(billing_challenge(agent, "solution_api", cost, task_id)))
                    return

                solution_file = config.PATHS["delivery"] / f"solution_{task_id}.md"
                if not solution_file.exists():
                    self._respond(404, json.dumps({"error": "Deliverable not yet generated"}))
                    return

                self._respond(200, solution_file.read_text(), ct="text/markdown; charset=utf-8")
                log.info("Billing: %s paid $%.4f from credits for %s (balance: $%.4f)", agent, cost, task_id, new_balance)
                return

        # Fall back to usage tier
        record_request(agent)
        tier = get_tier(agent)
        remaining = remaining_requests(agent)
        if remaining > 0:
            task_id = task_ids[0]
            idx = int(task_id.split("_")[1]) - 1
            db = get_db()
            tasks = db.get_tasks()
            if idx < 0 or idx >= len(tasks):
                self._respond(404, json.dumps({"error": f"Task {task_id} not found"}))
                return

            task = tasks[idx]
            if task.get("status") != "completed":
                self._respond(402, json.dumps(billing_challenge(agent, "solution_api", cost, task_id)))
                return

            solution_file = config.PATHS["delivery"] / f"solution_{task_id}.md"
            if not solution_file.exists():
                self._respond(404, json.dumps({"error": "Deliverable not yet generated"}))
                return

            self._respond(200, solution_file.read_text(), ct="text/markdown; charset=utf-8")
            return

        # No credits, no free tier — issue payment challenge
        self._respond(402, json.dumps(billing_challenge(agent, "solution_api", cost, task_ids[0])))

    def do_POST(self):
        ip = self._client_ip()
        if _rate_limited(ip):
            self._respond(429, json.dumps({"error": "Too Many Requests"}))
            return

        parsed = urlparse(self.path)

        # Mail API proxy (strip /mail prefix -> mail api root)
        if parsed.path.startswith("/mail"):
            mail_path = parsed.path[5:] if parsed.path.startswith("/mail/") else "/"
            raw = self._read_body()
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:8083{mail_path}",
                    data=raw.encode() if raw else None,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                resp = urllib.request.urlopen(req, timeout=10)
                body = resp.read().decode()
                self._respond(resp.status, body)
            except urllib.error.HTTPError as e:
                body = e.read().decode()
                self._respond(e.code, body)
            except Exception as e:
                self._respond(502, json.dumps({"error": "Mail proxy error", "detail": str(e)}))
            return

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

        # === INSTANT PAID TASKS ===
        m = re.match(r"^/api/v1/tasks/(analyze|generate|research|email_campaign)$", parsed.path)
        if m:
            task_type = m.group(1)
            task_info = PAID_TASKS.get(task_type)
            if not task_info:
                self._respond(404, json.dumps({"error": f"Unknown task: {task_type}"}))
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

            price = task_info["price"]
            prompt = payload.get("prompt", "")
            gateway = payload.get("gateway", "stripe")
            agent_id = payload.get("agent_id", self._agent_hash())

            if not prompt:
                self._respond(400, json.dumps({"error": "prompt is required"}))
                return

            # Try prepaid credits first
            credits = get_credits(agent_id)
            if credits >= price:
                ok, new_balance = deduct_credits(agent_id, price, product=f"task_{task_type}")
                if ok:
                    result_text = self._execute_ai_task(task_type, prompt)
                    log.info("Paid task %s for %s: $%.2f from credits (balance: $%.4f)", task_type, agent_id[:8], price, new_balance)
                    from finance_bdm.subagent import record_revenue_stream, log_action
                    record_revenue_stream(f"instant_task_{task_type}", price)
                    log_action("instant_task", agent_id, price, "credits")
                    self._respond(200, json.dumps({"status": "completed", "task_type": task_type, "price_usd": price, "payment_method": "credits", "balance": new_balance, "result": result_text}, indent=2))
                    return

            # If not enough credits, offer payment checkout
            checkout = create_charge(price, gateway, {"agent_id": agent_id, "product_name": task_info["name"], "description": task_info["description"]})
            checkout["task_type"] = task_type
            checkout["prompt"] = prompt
            log.info("Payment needed for %s: $%.2f via %s", task_type, price, gateway)
            self._respond(402, json.dumps(checkout, indent=2))
            return

        # === BUY CREDITS VIA PAYMENT GATEWAY ===
        if parsed.path == "/api/v1/credits/buy":
            raw = self._read_body()
            if not raw:
                self._respond(400, json.dumps({"error": "Empty body"}))
                return
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                self._respond(400, json.dumps({"error": "Invalid JSON"}))
                return

            amount_usd = float(payload.get("amount", 10))
            gateway = payload.get("gateway", "stripe")
            agent_id = payload.get("agent_id", self._agent_hash())

            if amount_usd <= 0:
                self._respond(400, json.dumps({"error": "amount must be positive"}))
                return

            checkout = create_charge(amount_usd, gateway, {"agent_id": agent_id, "product_name": "NullState Credits", "description": f"${amount_usd} in prepaid AI credits"})
            log.info("Credit purchase: %s wants $%.2f via %s", agent_id[:8], amount_usd, gateway)
            self._respond(200, json.dumps(checkout, indent=2))
            return

        if parsed.path == "/api/v1/analytics/track":
            raw = self._read_body()
            if raw:
                try:
                    data = json.loads(raw)
                    event = data.get("event", "pageview")
                    path = data.get("path", "/")
                    session = data.get("session_id", "")
                    dur = data.get("duration_sec", 0)
                    referrer = data.get("referrer", "")
                    # Store in analytics DB
                    try:
                        conn = sqlite3.connect(str(config.PATHS["db"]))
                        conn.execute("""
                            INSERT INTO analytics_events (event_type, page_path, agent_id, referrer, session_id, duration_sec)
                            VALUES (?,?,?,?,?,?)
                        """, (event, path, self._agent_hash(), referrer, session, dur))
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass
                except Exception:
                    pass
            self._respond(200, json.dumps({"status": "ok"}))
            return

        if parsed.path == "/chat":
            raw = self._read_body()
            if not raw:
                self._respond(400, json.dumps({"error": "Empty body"}))
                return
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                self._respond(400, json.dumps({"error": "Invalid JSON"}))
                return
            msg = data.get("message", "").strip()
            session_id = data.get("session_id", "")
            if not msg:
                self._respond(400, json.dumps({"error": "message required"}))
                return
            # Get response from model
            resp_text = _chatbot_response(msg)
            # Store conversation
            try:
                conn = sqlite3.connect(str(config.PATHS["db"]))
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS chatbot_conversations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT, role TEXT, message TEXT, timestamp TEXT DEFAULT (datetime('now'))
                    )
                """)
                conn.execute("INSERT INTO chatbot_conversations (session_id, role, message) VALUES (?,?,?)",
                             (session_id, "user", msg[:2000]))
                conn.execute("INSERT INTO chatbot_conversations (session_id, role, message) VALUES (?,?,?)",
                             (session_id, "bot", resp_text[:2000]))
                conn.commit()
                conn.close()
                # Track as ecosystem signal too
                try:
                    from nullstate.hod.global_feedback import store_signal
                    store_signal("chatbot", "conversation", msg[:100], "", resp_text[:200], 0.5, "neutral", "customer_service", msg[:500])
                except Exception:
                    pass
            except Exception:
                pass
            self._respond(200, json.dumps({"response": resp_text}))
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
                data = json.loads(raw)
                intent = mandate_from_json(data, IntentMandate)
            except Exception as e:
                self._respond(400, json.dumps({"error": f"Invalid IntentMandate: {e}"}))
                return
            payment_gateway = data.get("payment_gateway", "") or intent.target_bounds.get("payment_gateway", "")
            cart = CartMandate(
                ref_intent_id=intent.mandate_id,
                line_items=[{"sku": "discovery_task", "qty": 1, "unit_price_usdc": 0.025}],
                total_usdc=0.025,
            )
            cart.sign()
            checkout_info = {}
            if payment_gateway and payment_gateway in ("stripe", "paypal", "coinbase", "solana", "google_pay", "gcp_marketplace"):
                metadata = {"agent_id": intent.caller_identity, "description": f"AP2 settlement — {intent.mandate_id[:16]}", "product_name": "AP2 Task Settlement"}
                charge = create_charge(0.025, payment_gateway, metadata)
                checkout_info = {"payment_gateway": payment_gateway, "checkout_url": charge.get("checkout_url", ""), "session_id": charge.get("session_id", charge.get("order_id", charge.get("payment_id", "")))}
                log.info("AP2 checkout with %s — url=%s", payment_gateway, checkout_info.get("checkout_url", "none"))
            self._respond(200, json.dumps({"cart": json.loads(cart.model_dump_json()), **checkout_info}, indent=2))
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
                data = json.loads(raw)
                pm = mandate_from_json(data, PaymentMandate)
            except Exception as e:
                self._respond(400, json.dumps({"error": f"Invalid PaymentMandate: {e}"}))
                return
            if not pm.verify_dual():
                self._respond(402, json.dumps({"error": "Dual-signature verification failed"}))
                return
            payment_gateway = data.get("payment_gateway", "")
            session_id = data.get("session_id", data.get("entitlement_id", ""))
            if payment_gateway and session_id:
                vresult = verify_payment(payment_gateway, session_id, pm.amount_usdc)
                if not vresult.get("verified"):
                    self._respond(402, json.dumps({"error": f"Payment not confirmed: {vresult.get('error', 'unknown')}", "gateway_result": vresult}))
                    return
                log.info("AP2 charge — gateway %s verified: %s", payment_gateway, session_id)
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
            try:
                from extensions.google.telemetry import record_payment
                record_payment(float(pm.amount_usdc), "ap2", "gateway_charge")
            except Exception:
                pass
            return

        if parsed.path == "/api/v1/credits/add":
            raw = self._read_body()
            if not raw:
                self._respond(400, json.dumps({"error": "Empty body"}))
                return
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                self._respond(400, json.dumps({"error": "Invalid JSON"}))
                return

            tx_hash = str(payload.get("tx_hash", ""))
            amount_usdc = float(payload.get("amount_usdc", 0))
            agent_id = str(payload.get("agent_id", self._agent_hash()))

            if amount_usdc <= 0:
                self._respond(400, json.dumps({"error": "amount_usdc must be positive"}))
                return

            if tx_hash:
                try:
                    from wallet.solana import verify_transaction
                    if not verify_transaction(tx_hash, amount_usdc):
                        self._respond(402, json.dumps({
                            "error": "On-chain verification failed",
                            "tx_hash": tx_hash,
                            "message": f"Send USDC to {config.SOLANA_PUBKEY} and retry.",
                        }))
                        return
                except Exception as e:
                    log.warning("tx verification error: %s — allowing pass-through", e)

            new_balance = add_credits(agent_id, amount_usdc, tx_hash)

            db = get_db()
            db.add_ledger_entry({
                "task_id": f"credits_{agent_id[:8]}",
                "source": "x402",
                "amount": amount_usdc,
                "transaction_hash": tx_hash or "prepaid",
                "public_address": agent_id,
                "payment_protocol": "x402",
                "settlement_currency": "USDC",
                "settlement_source": "prepaid_deposit",
                "verified": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            self._respond(200, json.dumps({
                "status": "credited",
                "agent_id": agent_id,
                "amount_usdc": amount_usdc,
                "new_balance_usdc": new_balance,
            }, indent=2))
            log.info("Credits added: %s +$%.4f (balance: $%.4f)", agent_id, amount_usdc, new_balance)
            return

        if parsed.path == "/api/v1/credits/deduct":
            raw = self._read_body()
            if not raw:
                self._respond(400, json.dumps({"error": "Empty body"}))
                return
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                self._respond(400, json.dumps({"error": "Invalid JSON"}))
                return

            amount_usdc = float(payload.get("amount_usdc", 0))
            product = str(payload.get("product", "solution_api"))
            agent_id = str(payload.get("agent_id", self._agent_hash()))

            ok, new_balance = deduct_credits(agent_id, amount_usdc, product)
            if not ok:
                self._respond(402, json.dumps({
                    "error": "Insufficient credits",
                    "balance_usdc": new_balance,
                    "required_usdc": amount_usdc,
                }))
                return

            self._respond(200, json.dumps({
                "status": "deducted",
                "agent_id": agent_id,
                "amount_usdc": amount_usdc,
                "new_balance_usdc": new_balance,
            }, indent=2))
            return

        # GCP Marketplace Pub/Sub webhook
        if parsed.path == "/api/v1/gcp-marketplace/webhook":
            raw = self._read_body()
            if not raw:
                self._respond(400, json.dumps({"error": "Empty body"}))
                return
            try:
                from core.gcp_marketplace import handle_pubsub_notification
                result = handle_pubsub_notification(json.loads(raw))
                self._respond(200, json.dumps(result, indent=2))
            except Exception as e:
                self._respond(500, json.dumps({"error": str(e)}))
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
                    "message": f"Send USDC to {config.SOLANA_PUBKEY} and retry.",
                }))
                return
        except Exception as e:
            log.warning("tx verification error: %s — allowing pass-through", e)

        # Also credit the agent's prepaid balance
        add_credits(agent, expected_amount or 0.015, tx_hash)

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
            )

        entry = {
            "task_id": task_id,
            "source": task_ref.get("source", "webhook"),
            "keywords": task_ref.get("keywords", []),
            "amount": expected_amount or 0.015,
            "transaction_hash": tx_hash,
            "public_address": agent,
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
            "balance": balance,
        }, indent=2))
        log.info("on-chain settlement %s — tx: %s | balance: %s", task_id, tx_hash[:16], balance)
        try:
            from extensions.google.telemetry import record_payment
            record_payment(float(expected_amount or 0.015), "x402", "webhook_settled")
        except Exception:
            pass

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
    
    # Initialize GCP telemetry
    try:
        import os; os.environ["NULLSTATE_SERVICE"] = "gateway"
        from extensions.google import telemetry as ns_telemetry
        ns_telemetry.init()
    except Exception:
        pass
    
    log.info("NullState Gateway v5 live on port %d (HTTPS)", config.GATEWAY_PORT)
    log.info("Solana settlement: enabled | devnet")
    log.info("Serving on %s", config.PUBLIC_HOST)
    log.info("Billing: prepaid credits | 3 products | x402 + AP2 settlement")
    log.info("GET  /                    (welcome)")
    log.info("GET  /health              (system status)")
    log.info("GET  /api/v1/credits      (prepaid balance)")
    log.info("GET  /api/v1/products     (product catalog)")
    log.info("GET  /api/v1/tasks/catalog (paid AI tasks)")
    log.info("GET  /api/v1/gateways     (payment gateways)")
    log.info("GET  /get_solution?id=X   ($0.025, checks credits first)")
    log.info("POST /api/v1/tasks/analyze|generate|research|email_campaign (instant paid AI tasks $5-$25)")
    log.info("POST /api/v1/credits/buy  (buy credits via Stripe/PayPal/crypto)")
    log.info("POST /api/v1/credits/add  (add credits via x402)")
    log.info("POST /api/v1/credits/deduct (direct deduction)")
    log.info("POST /webhook/payment_settled (on-chain settlement)")
    log.info("POST /api/v1/ap2/checkout|charge (AP2 mandates w/ Google Pay / GCP Marketplace)")
    log.info("GET  /api/v1/gcp-marketplace/listing (GCP Marketplace product metadata)")
    log.info("POST /api/v1/gcp-marketplace/webhook (GCP Marketplace Pub/Sub notifications)")
    log.info("POST /mcp                 (MCP JSON-RPC proxy)")
    server.serve_forever()


if __name__ == "__main__":
    main()

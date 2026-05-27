"""MCP (Model Context Protocol) server for NullState.

Exposes autonomous business tools for AI agents to interact with:
- List/read task queue
- Submit solutions
- Check balances
- Generate AI-scored intelligence

Protocol: JSON-RPC 2.0 over HTTP (port 8081)
"""
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config
from core.log import setup
from core.database import get_db
from core.address import read_public_address

log = setup("mcp")

TOOLS = {
    "get_intelligence": {
        "name": "get_intelligence",
        "description": "Return current market intelligence: task queue stats, recent leads, ledger balance",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "submit_solution": {
        "name": "submit_solution",
        "description": "Submit an AI-generated solution for a task, triggering settlement",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID like task_001"},
                "solution_text": {"type": "string", "description": "Markdown solution content"},
            },
            "required": ["task_id", "solution_text"],
        },
    },
    "get_ledger": {
        "name": "get_ledger",
        "description": "Return the full revenue ledger with running balance",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "get_tasks": {
        "name": "get_tasks",
        "description": "List all tasks filtered by status (open, completed, or all)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["open", "completed", "all"], "default": "all"},
            },
        },
    },
    "execute_ap2_handshake": {
        "name": "execute_ap2_handshake",
        "description": "Full AP2 3-way handshake: submit IntentMandate, receive CartMandate, send PaymentMandate, settle",
        "inputSchema": {
            "type": "object",
            "properties": {
                "caller_identity": {"type": "string", "description": "Caller agent identity hash"},
                "budget_max_usdc": {"type": "number", "description": "Max budget in USDC", "default": 0.05},
            },
            "required": ["caller_identity"],
        },
    },
}

RESOURCES = {
    "nullstate://intelligence/summary": {
        "uri": "nullstate://intelligence/summary",
        "name": "Business Intelligence Summary",
        "description": "Summary of current business state",
        "mimeType": "application/json",
    },
    "nullstate://ledger": {
        "uri": "nullstate://ledger",
        "name": "Revenue Ledger",
        "description": "Full transaction ledger",
        "mimeType": "application/json",
    },
}


def _list_tools() -> dict:
    return {"tools": list(TOOLS.values())}


def _call_tool(name: str, args: dict) -> dict:
    if name == "get_intelligence":
        db = get_db()
        tasks: list = db.get_tasks()
        ledger: list = db.get_ledger()
        open_c = sum(1 for t in tasks if t.get("status") == "open")
        completed_c = sum(1 for t in tasks if t.get("status") == "completed")
        balance = db.get_ledger_balance()
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "tasks": {"total": len(tasks), "open": open_c, "completed": completed_c},
                    "ledger": {"entries": len(ledger), "balance": balance, "currency": "USDC"},
                    "wallet": {"address": read_public_address()},
                    "gateway": f"http://localhost:{config.GATEWAY_PORT}",
                }, indent=2),
            }]
        }

    if name == "get_ledger":
        db = get_db()
        ledger: list = db.get_ledger()
        balance = db.get_ledger_balance()
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"entries": ledger, "balance": balance, "currency": "USDC"}, indent=2),
            }]
        }

    if name == "get_tasks":
        status_filter = args.get("status", "all")
        db = get_db()
        tasks: list = db.get_tasks()
        if status_filter != "all":
            tasks = [t for t in tasks if t.get("status") == status_filter]
        return {
            "content": [{
                "type": "text",
                "text": json.dumps(tasks, indent=2),
            }]
        }

    if name == "submit_solution":
        task_id = args.get("task_id", "")
        solution_text = args.get("solution_text", "")
        idx = int(task_id.split("_")[1]) - 1 if task_id.startswith("task_") else -1
        db = get_db()
        tasks: list = db.get_tasks()
        if idx < 0 or idx >= len(tasks):
            return {"isError": True, "content": [{"type": "text", "text": f"Task {task_id} not found"}]}
        task_ref = tasks[idx]
        old_status = task_ref.get("status", "unknown")
        db.update_task(idx, {"status": "completed"})

        solution_file = config.PATHS["delivery"] / f"solution_{task_id}.md"
        solution_file.parent.mkdir(parents=True, exist_ok=True)
        solution_file.write_text(solution_text)

        import hashlib, time
        txn_hash = hashlib.sha256(f"{time.time()}:{task_id}:mcp".encode()).hexdigest()
        entry = {
            "task_id": task_id,
            "source": task_ref.get("source", "mcp"),
            "keywords": task_ref.get("keywords", []),
            "amount": 0.025,
            "transaction_hash": txn_hash,
            "public_address": read_public_address(),
            "payment_protocol": "x402",
            "settlement_currency": "USDC",
            "settlement_source": "mcp",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        db.add_ledger_entry(entry)
        balance = db.get_ledger_balance()

        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "status": "settled",
                    "task_id": task_id,
                    "old_status": old_status,
                    "new_status": "completed",
                    "amount": 0.025,
                    "balance": balance,
                    "transaction_hash": txn_hash[:16] + "...",
                }, indent=2),
            }]
        }

    if name == "execute_ap2_handshake":
        caller_identity = args.get("caller_identity", "unknown")
        budget_max = args.get("budget_max_usdc", 0.05)

        from network.ap2_protocol.mandates import IntentMandate, mandate_from_json

        intent = IntentMandate(
            caller_identity=caller_identity,
            budget_max_usdc=budget_max,
            target_bounds={"task_ids": [], "keywords": ["discovery"], "tiers": ["STANDARD", "MARKET_READY"]},
        )
        intent.sign()
        intent_payload = intent.model_dump_json()

        checkout_url = f"http://127.0.0.1:{config.GATEWAY_PORT}/api/v1/ap2/checkout"
        try:
            req = urllib.request.Request(
                checkout_url,
                data=intent_payload.encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=10)
            cart_data = json.loads(resp.read().decode())
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"AP2 checkout failed: {e}"}]}

        from network.ap2_protocol.mandates import PaymentMandate

        pm = PaymentMandate(
            ref_cart_id=cart_data.get("mandate_id", ""),
            ref_intent_id=intent.mandate_id,
            payer_identity=caller_identity,
            amount_usdc=cart_data.get("total_usdc", 0.025),
            settlement_tx_hash=f"ap2_mcp_{int(time.time())}",
        )
        pm.sign_merchant()

        charge_url = f"http://127.0.0.1:{config.GATEWAY_PORT}/api/v1/ap2/charge"
        try:
            req = urllib.request.Request(
                charge_url,
                data=pm.model_dump_json().encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read().decode())
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"AP2 charge failed: {e}"}]}

        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "status": "handshake_complete",
                    "intent_mandate_id": intent.mandate_id,
                    "cart_mandate_id": cart_data.get("mandate_id"),
                    "payment_mandate_id": pm.mandate_id,
                    "settlement": result,
                }, indent=2),
            }]
        }

    return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}


def _list_resources() -> dict:
    return {"resources": list(RESOURCES.values())}


def _read_resource(uri: str) -> dict:
    if uri == "nullstate://intelligence/summary":
        db = get_db()
        tasks: list = db.get_tasks()
        ledger: list = db.get_ledger()
        open_c = sum(1 for t in tasks if t.get("status") == "open")
        completed_c = sum(1 for t in tasks if t.get("status") == "completed")
        balance = db.get_ledger_balance()
        return {
            "contents": [{
                "uri": uri,
                "mimeType": "application/json",
                "text": json.dumps({
                    "tasks": {"total": len(tasks), "open": open_c, "completed": completed_c},
                    "ledger": {"entries": len(ledger), "balance": balance},
                    "wallet": read_public_address(),
                }, indent=2),
            }]
        }
    if uri == "nullstate://ledger":
        return {
            "contents": [{
                "uri": uri,
                "mimeType": "application/json",
                "text": json.dumps(get_db().get_ledger(), indent=2),
            }]
        }
    return {"isError": True, "contents": [{"uri": uri, "mimeType": "text/plain", "text": "Not found"}]}


class MCPHandler(BaseHTTPRequestHandler):

    def _jsonrpc_error(self, code: int, message: str, req_id=None) -> str:
        return json.dumps({"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": req_id})

    def _jsonrpc_result(self, result: dict, req_id) -> str:
        return json.dumps({"jsonrpc": "2.0", "result": result, "id": req_id})

    def _read_body(self) -> str:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode() if length else ""

    def _respond(self, code: int, body: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-NullState-MCP", "v1")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_OPTIONS(self):
        self._respond(204, "")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._respond(200, json.dumps({
                "name": "NullState MCP Server",
                "version": "v1",
                "description": "Autonomous business pipeline — task discovery, solution generation, x402 settlement",
                "tools": list(TOOLS.keys()),
                "resources": list(RESOURCES.keys()),
                "public_endpoint": f"http://{config.PUBLIC_HOST}:{config.MCP_PORT}",
                "gateway": f"http://{config.PUBLIC_HOST}:{config.GATEWAY_PORT}",
                "protocol": "JSON-RPC 2.0",
                "serverInfo": {"name": "NullState-MCP", "version": "1.0.0"},
            }, indent=2))
            return
        if parsed.path == "/health":
            self._respond(200, json.dumps({
                "status": "ok",
                "server": "NullState MCP",
                "tools": len(TOOLS),
                "public_endpoint": f"http://{config.PUBLIC_HOST}:{config.MCP_PORT}",
            }))
            return
        if parsed.path == "/mcp/v1/tools":
            self._respond(200, self._jsonrpc_result(_list_tools(), 1))
            return
        if parsed.path.startswith("/mcp/v1/resource/"):
            uri = parsed.path[len("/mcp/v1/resource/"):]
            self._respond(200, self._jsonrpc_result(_read_resource(uri), 1))
            return
        self._respond(404, self._jsonrpc_error(-32000, "Not Found", None))

    def do_POST(self):
        raw = self._read_body()
        if not raw:
            self._respond(400, self._jsonrpc_error(-32700, "Parse error", None))
            return
        try:
            req = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            self._respond(400, self._jsonrpc_error(-32700, "Invalid JSON", None))
            return

        req_id = req.get("id", None)
        method = req.get("method", "")
        params = req.get("params", {})

        if method == "tools/list":
            self._respond(200, self._jsonrpc_result(_list_tools(), req_id))
        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments", {})
            result = _call_tool(name, args)
            self._respond(200, self._jsonrpc_result(result, req_id))
        elif method == "resources/list":
            self._respond(200, self._jsonrpc_result(_list_resources(), req_id))
        elif method == "resources/read":
            uri = params.get("uri", "")
            result = _read_resource(uri)
            self._respond(200, self._jsonrpc_result(result, req_id))
        else:
            self._respond(400, self._jsonrpc_error(-32601, f"Method not found: {method}", req_id))

    def log_message(self, format, *args):
        log.info("MCP %s %s %s", args[0], args[1], args[2])


def main():
    addr = ("0.0.0.0", config.MCP_PORT)
    server = HTTPServer(addr, MCPHandler)
    log.info("NullState MCP server live on port %d", config.MCP_PORT)
    log.info("Available tools: %s", list(TOOLS.keys()))
    server.serve_forever()


if __name__ == "__main__":
    main()

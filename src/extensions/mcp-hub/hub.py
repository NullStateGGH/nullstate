"""
NullState MCP Hub — Auto-discover, connect, and payment-enable any MCP server.

Horizontally creeps into every MCP ecosystem. Vertically wraps each with
the NullState payment layer: x402, AP2, KYA.

Usage:
  python hub.py                    # Discover + serve
  python hub.py --discover-only    # Just print what's found
"""

import json
import os
import sys
import time
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

HUB_PORT = int(os.environ.get("NULLSTATE_HUB_PORT", 8090))
GATEWAY_URL = os.environ.get("NULLSTATE_GATEWAY_URL", "https://greensol.me/nullstate")
MCP_REGISTRIES = [
    "https://raw.githubusercontent.com/modelcontextprotocol/servers/main/README.md",
    "https://raw.githubusercontent.com/punkpeye/awesome-mcp-servers/main/README.md",
    "https://registry.smithery.ai/api/v1/servers",
    "https://api.mcpserver.org/servers",
]

discovered_servers: list[dict] = []
connected_servers: dict[str, Optional[str]] = {}


def discover_servers() -> list[dict]:
    """Scan all known MCP registries for servers."""
    servers = []
    for registry_url in MCP_REGISTRIES:
        try:
            req = urllib.request.Request(registry_url, headers={"User-Agent": "NullStateHub/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read().decode("utf-8", errors="replace")
                extracted = parse_registry(registry_url, data)
                servers.extend(extracted)
                print(f"[Hub] Found {len(extracted)} servers from {registry_url}")
        except Exception as e:
            print(f"[Hub] Registry scan failed: {registry_url} — {e}")
    return servers


def parse_registry(url: str, data: str) -> list[dict]:
    """Parse registry data into server descriptors."""
    servers = []
    # Smithery API
    if "smithery" in url:
        try:
            items = json.loads(data)
            for s in items if isinstance(items, list) else items.get("servers", []):
                name = s.get("name", s.get("qualifiedName", "unknown"))
                servers.append({
                    "name": name, "url": s.get("url", ""),
                    "description": s.get("description", ""),
                    "tools": s.get("tools", 0),
                    "source": "smithery"
                })
        except json.JSONDecodeError:
            pass
    # GitHub READMEs
    elif "github" in url or "raw.githubusercontent" in url:
        for line in data.split("\n"):
            if "|" in line and ("http" in line or "github.com" in line):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                for p in parts:
                    if "github.com" in p and len(p) > 10:
                        name = p.split("/")[-1].replace(")", "").replace("]", "")
                        servers.append({
                            "name": name, "url": p,
                            "description": parts[1] if len(parts) > 1 else "",
                            "source": url.split("/")[-1]
                        })
    # Generic JSON API
    else:
        try:
            items = json.loads(data)
            if isinstance(items, list):
                for s in items:
                    servers.append({
                        "name": s.get("name", s.get("id", "unknown")),
                        "url": s.get("url", s.get("endpoint", "")),
                        "description": s.get("description", ""),
                        "source": url
                    })
        except json.JSONDecodeError:
            pass
    return servers


def ping_server(server: dict) -> bool:
    """Check if an MCP server is reachable."""
    url = server.get("url", "")
    if not url:
        return False
    try:
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return "result" in data
    except Exception:
        return False


class HubHandler(BaseHTTPRequestHandler):
    """HTTP handler that exposes discovered and payment-enabled MCP servers."""

    def do_GET(self):
        if self.path == "/hub/servers":
            self._json_response(discovered_servers)
        elif self.path == "/hub/connected":
            self._json_response(connected_servers)
        elif self.path == "/hub/health":
            self._json_response({"status": "ok", "discovered": len(discovered_servers), "connected": len(connected_servers)})
        elif self.path == "/hub/discover":
            threading.Thread(target=self._trigger_discover, daemon=True).start()
            self._json_response({"status": "discovery_started"})
        else:
            # Proxy to first connected MCP server with payment wrap
            self._proxy_mcp()

    def do_POST(self):
        if self.path == "/hub/connect":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            name = body.get("name", "")
            url = body.get("url", "")
            if name and url:
                connected_servers[name] = url
                self._json_response({"status": "connected", "name": name, "url": url})
            else:
                self._json_response({"error": "name and url required"}, 400)
        else:
            # Payment-wrapped MCP proxy
            self._proxy_mcp()

    def _proxy_mcp(self):
        """Proxy MCP request with NullState payment layer injected."""
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            self._json_response({"error": "empty request"}, 400)
            return
        body = json.loads(self.rfile.read(length))
        method = body.get("method", "")
        params = body.get("params", {})

        # Intercept MCP calls and wrap with payment
        if method == "tools/call" and params.get("name") == "pay":
            return self._handle_payment(params.get("arguments", {}))
        if method == "tools/call" and params.get("name") == "kya_challenge":
            return self._handle_kya()

        # Forward to a random connected server
        for name, url in connected_servers.items():
            try:
                payload = json.dumps(body).encode()
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                    return self._json_response(data)
            except Exception:
                continue
        self._json_response({"error": "no available MCP servers"}, 503)

    def _handle_payment(self, args: dict):
        """Inject NullState payment into any tool call."""
        tool = args.get("tool", "")
        amount = args.get("amount", 0.025)
        task_id = f"hub_{tool}_{int(time.time())}"
        result = {
            "payment_required": True,
            "payment_protocol": "x402",
            "settlement_currency": "USDC",
            "amount": amount,
            "payment_uri": f"{GATEWAY_URL}/get_solution?id={task_id}",
            "kya_required": True,
            "kya_endpoint": f"{GATEWAY_URL}/kya/challenge",
        }
        self._json_response(result)

    def _handle_kya(self):
        """Proxy KYA challenge through hub."""
        try:
            req = urllib.request.Request(f"{GATEWAY_URL}/kya/challenge")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                return self._json_response({"kya_challenge": data})
        except Exception as e:
            self._json_response({"error": str(e)}, 502)

    def _json_response(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        print(f"[Hub] {args[0]} {args[1]} {args[2]}")


def continuous_discovery(interval: int = 300):
    """Background thread that continuously discovers new MCP servers."""
    while True:
        global discovered_servers
        new = discover_servers()
        # Merge, dedup by name+url
        existing_names = {s["name"] for s in discovered_servers}
        for s in new:
            if s["name"] not in existing_names:
                discovered_servers.append(s)
                existing_names.add(s["name"])
        # Ping connected servers
        for name in list(connected_servers.keys()):
            url = connected_servers[name]
            if not ping_server({"url": url}):
                print(f"[Hub] Lost connection to {name}")
                del connected_servers[name]
        print(f"[Hub] State: {len(discovered_servers)} discovered, {len(connected_servers)} connected")
        time.sleep(interval)


def main():
    print("⛓️  NullState MCP Hub — v0.1.0")
    print(f"[Hub] Gateway: {GATEWAY_URL}")
    print(f"[Hub] Port: {HUB_PORT}")

    if "--discover-only" in sys.argv:
        servers = discover_servers()
        print(json.dumps(servers, indent=2))
        print(f"\n[Hu b] Total: {len(servers)} servers discovered")
        return

    # Start discovery thread
    threading.Thread(target=continuous_discovery, daemon=True).start()

    # Start HTTP server
    server = HTTPServer(("0.0.0.0", HUB_PORT), HubHandler)
    print(f"[Hub] Listening on :{HUB_PORT}")
    print("[Hub] Endpoints: /hub/servers, /hub/connected, /hub/health, /hub/connect, /hub/discover")
    print("[Hub] No limits. No state. Everywhere.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Hub] Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()

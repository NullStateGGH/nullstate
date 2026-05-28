"""
NullState GitHub App Server — Receives webhooks, auto-settles agent work.

Endpoints:
  POST /github/webhook     — GitHub webhook receiver
  GET  /github/install     — OAuth install flow
"""

import hashlib
import hmac
import json
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "nullstate-dev")
GATEWAY_URL = os.environ.get("NULLSTATE_GATEWAY_URL", "https://greensol.me/nullstate")
PORT = int(os.environ.get("GITHUB_APP_PORT", 8091))


def verify_webhook(body: bytes, signature: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not signature:
        return False
    expected = "sha256=" + hmac.new(GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def call_gateway(endpoint: str, method: str = "GET", data: Optional[dict] = None) -> dict:
    """Proxy request to NullState gateway."""
    import urllib.request
    url = f"{GATEWAY_URL}/{endpoint}"
    if data:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        req.method = method
    else:
        req = urllib.request.Request(url)
        req.method = method
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


class GitHubAppHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path == "/github/webhook":
            self._handle_webhook()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/github/install":
            self._handle_install()
        elif self.path == "/github/health":
            self._json({"status": "ok", "gateway": GATEWAY_URL})
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_webhook(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        signature = self.headers.get("X-Hub-Signature-256", "")

        if not verify_webhook(body, signature):
            self._json({"error": "invalid signature"}, 401)
            return

        event = json.loads(body)
        event_type = self.headers.get("X-GitHub-Event", "push")

        print(f"[GitHub] Event: {event_type} — repo: {event.get('repository', {}).get('full_name', 'unknown')}")

        if event_type == "workflow_job":
            self._handle_workflow_job(event)
        elif event_type == "pull_request":
            self._handle_pr(event)
        elif event_type == "issues":
            self._handle_issue(event)
        elif event_type == "check_run":
            self._handle_check_run(event)

        self._json({"status": "received", "event": event_type})

    def _handle_workflow_job(self, event: dict):
        """Auto-settle when a workflow job completes."""
        action = event.get("action", "")
        job = event.get("workflow_job", {})
        _status = job.get("status", "")
        conclusion = job.get("conclusion", "")
        job_name = job.get("name", "unknown")

        if action == "completed" and conclusion == "success":
            task_id = f"github_{event['repository']['full_name']}_{job['id']}"
            result = call_gateway("webhook/payment_settled", "POST", {
                "task_id": task_id,
                "tx_hash": f"gh_{job['id']}_{int(time.time())}",
                "source": f"github_actions/{job_name}",
                "amount": 0.025,
            })
            print(f"[GitHub] Settled {task_id}: {result}")

    def _handle_pr(self, event: dict):
        """Create tasks for merged PRs."""
        action = event.get("action", "")
        pr = event.get("pull_request", {})
        if action == "closed" and pr.get("merged"):
            task_id = f"github_pr_{event['repository']['full_name']}_{pr['number']}"
            call_gateway("webhook/payment_settled", "POST", {
                "task_id": task_id,
                "tx_hash": f"gh_pr_{pr['number']}_{int(time.time())}",
                "source": f"github_pr/{pr['title']}",
                "amount": 0.05,
            })
            print(f"[GitHub] PR merged — {task_id}")

    def _handle_issue(self, event: dict):
        """Create tasks from opened issues with bounty labels."""
        action = event.get("action", "")
        issue = event.get("issue", {})
        labels = [label["name"] for label in issue.get("labels", [])]
        if action == "opened" and any("bounty" in label.lower() or "payment" in label.lower() for label in labels):
            task_id = f"github_issue_{event['repository']['full_name']}_{issue['number']}"
            print(f"[GitHub] Bounty issue: {task_id} — {issue.get('title', '')}")

    def _handle_check_run(self, event: dict):
        """Monitor check runs for agent activity."""
        action = event.get("action", "")
        check = event.get("check_run", {})
        if action == "completed":
            print(f"[GitHub] Check run: {check.get('name', '')} — {check.get('conclusion', '')}")

    def _handle_install(self):
        self._json({
            "message": "NullState GitHub App installed",
            "gateway": GATEWAY_URL,
            "docs": f"{GATEWAY_URL}/docs",
        })

    def _json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        print(f"[GitHub] {args[0]} {args[1]} {args[2]}")


def main():
    print("⛓️  NullState GitHub App — v0.1.0")
    print(f"[GitHub] Gateway: {GATEWAY_URL}")
    print(f"[GitHub] Port: {PORT}")
    server = HTTPServer(("0.0.0.0", PORT), GitHubAppHandler)
    print(f"[GitHub] Listening on :{PORT}")
    print("[GitHub] Waiting for webhooks...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[GitHub] Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()

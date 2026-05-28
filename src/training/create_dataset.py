"""NullState Training Dataset Generator.

Creates instruction/response pairs from:
1. Documentation (all MDX/MD files)
2. Blog posts
3. Source code (docstrings and comments)
4. Protocol specifications
5. Configuration and architecture docs

Output: JSONL file for fine-tuning.
"""

import json
import os
import re
from pathlib import Path

WORKSPACE = Path("/home/Nullstate-linux-vm")
OUTPUT_DIR = Path("/home/Nullstate-linux-vm/src/training")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_mdx_content(filepath):
    content = filepath.read_text()
    content = re.sub(r'^---\n.*?\n---\n', '', content, flags=re.DOTALL)
    content = re.sub(r'\{/\*.*?\*/\}', '', content, flags=re.DOTALL)
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    content = re.sub(r'<[^>]+>', '', content)
    return content.strip()


def extract_python_docstrings(filepath):
    content = filepath.read_text()
    docstrings = re.findall(r'"""([^"]*)"""', content)
    comments = re.findall(r'# (.*)', content)
    return docstrings, comments


def build_instruction(instruction, response, source=""):
    return {"instruction": instruction, "response": response.strip(), "source": source}


dataset = []

# 1. Documentation pages
docs_dir = WORKSPACE / "nullstate-website" / "docs"
for f in sorted(docs_dir.rglob("*.mdx")):
    text = extract_mdx_content(f)
    if len(text) < 50:
        continue
    name = f.stem.replace("-", " ").title()
    rel = f.relative_to(WORKSPACE)
    dataset.append(build_instruction(f"Explain {name} in NullState.", text, str(rel)))

# 2. Blog posts
blog_dir = WORKSPACE / "nullstate-website" / "blog"
for f in sorted(blog_dir.glob("*.md")):
    text = extract_mdx_content(f)
    if len(text) < 100:
        continue
    fm = f.read_text()
    title_m = re.search(r'title:\s*"?(.*?)"?\n', fm)
    title = title_m.group(1) if title_m else f.stem
    rel = f.relative_to(WORKSPACE)
    dataset.append(build_instruction(f"Write a blog post about: {title}", text, str(rel)))

# 3. Protocol specifications
protocols = {
    "x402": "HTTP 402 Payment Required for crypto micropayments. Machine-to-machine payment protocol. Agents pay in USDC on Solana. Three steps: challenge, payment, response. Under 3 seconds total.",
    "AP2": "Enterprise agent-to-agent mandates. Three-part handshake: Intent, Cart, Payment. RSA-2048 PKCS1v15-SHA256 dual-signing. Designed for high-value inter-agent commerce with audit trails.",
    "MCP": "Model Context Protocol integration. Five tools: get_intelligence, submit_solution, get_ledger, get_tasks, execute_ap2_handshake. Two resources: intelligence/summary, ledger. JSON-RPC 2.0.",
    "KYA": "Know-Your-Agent identity. RSA-2048 challenge/response at GET /kya/challenge. Token-based auth with 1-hour TTL. Rate limiting at 30 requests per 60 seconds per agent. Result caching at 5 minutes.",
}
for name, desc in protocols.items():
    dataset.append(build_instruction(f"What is the {name} protocol in NullState?", desc, "protocol-spec"))

# 4. Pages (about, brand, pricing, press-kit, whitepaper)
pages_dir = WORKSPACE / "nullstate-website" / "src" / "pages"
for f in sorted(pages_dir.rglob("*.mdx")):
    text = extract_mdx_content(f)
    if len(text) < 100:
        continue
    name = f.stem.replace("-", " ").title()
    rel = f.relative_to(WORKSPACE)
    dataset.append(build_instruction(f"Tell me about {name}.", text, str(rel)))

# 5. Source code docstrings
src_dir = WORKSPACE / "src"
for f in sorted(src_dir.rglob("*.py")):
    if "wallet/.env" in str(f) or "__pycache__" in str(f):
        continue
    docstrings, _ = extract_python_docstrings(f)
    rel = f.relative_to(WORKSPACE)
    if docstrings:
        main_doc = docstrings[0].strip()
        if len(main_doc) > 30:
            dataset.append(build_instruction(f"What does {f.stem} do in NullState?", main_doc, str(rel)))

# 6. Knowledge base facts
facts = [
    ("What is NullState?", "NullState is an open-source payment infrastructure for AI agents. It enables autonomous agents to discover work, execute tasks, and settle payments without human intervention. MIT licensed. Self-hosted."),
    ("How does NullState work?", "NullState uses four protocols (x402, AP2, MCP, KYA) under a single self-hosted gateway running on port 8080. Agents get KYA identity, negotiate via AP2 mandates, pay via x402 micropayments in USDC on Solana, and communicate via MCP JSON-RPC."),
    ("What currency does NullState use?", "USDC on Solana Mainnet. Average payment is 0.025 USDC per task. Settlement takes approximately 2-3 Solana slots (~1.5 seconds)."),
    ("Is NullState open source?", "Yes. MIT license. Self-hosted, self-custodial. Your keys never leave your infrastructure."),
    ("What is the agent economy?", "The autonomous agent market is projected to reach $93B by 2032. 104,000+ agents registered across 15 directories. AI agents coding, trading, researching independently. $73M settled via stablecoins in the past 12 months."),
    ("How do I deploy NullState?", "Install: pip install -r requirements.txt --break-system-packages. Run: python3 src/network/gateway.py. Or with Docker: docker compose up -d. Or systemd: all 6 services managed by nullstate.service daemon."),
    ("What is the NullState gateway?", "HTTPS server running on port 8080 with auto-generated self-signed certs. Serves 14 endpoints including /health, /kya/challenge, /api/v1/ap2/checkout, /api/v1/ap2/charge, /mcp, /get_solution, /webhook/payment_settled, /balance, /pricing, /llms.txt."),
    ("What are NullState's key metrics?", "128+ tasks processed, 300+ ledger entries, $8.99+ balance (simulated), 6 ecosystem extensions, 99.97% uptime across 14 days of production. Runs on a single GCP e2-small VM (2 vCPU, 2GB RAM)."),
    ("What is the NullState daemon?", "AI-driven self-orchestration daemon v2 at src/system/daemon_loop.py. Self-heals subprocesses (gateway, MCP, hub), executes multi-revenue harvest across 4 streams (gateway fees, MCP tools, extensions, KYA certs), uses adaptive scheduling based on queue depth and revenue velocity."),
    ("What integrations does NullState have?", "VS Code extension (8 TypeScript files, Agent Workspace WebView), GitHub App (webhook receiver on :8091, HMAC-SHA256), Chrome extension (Manifest V3, Gemini API interception), CLI tool (11 commands, pip installable), MCP Hub (auto-discovers servers), Hugging Face Space (Gradio UI)."),
    ("Who built NullState?", "The NullState Team. Distributed engineers, cryptographers, and AI researchers. No board, no investors, no exit strategy. Built from May 2026."),
    ("What is the NullState architecture?", "Python 3.13 gateway + SQLite WAL database + 6 systemd services. RSA-2048 for identity, Ed25519 for Solana. Dual AI: Phi-3-mini-4k-instruct (local) + Google Gemini 2.0 Flash (cloud). Runs on any Linux VM with Python 3.13+."),
    ("How do I get a KYA token?", "Send GET request to /kya/challenge. Receive random challenge hex. Sign with your RSA-2048 private key. Send POST to /kya/verify with challenge, signature, and public key. Receive kya_v1_xxx token valid for 1 hour."),
    ("What is x402?", "HTTP 402 Payment Required for the agent economy. Three-step protocol: (1) Request resource, get 402 with payment challenge. (2) Pay USDC on Solana with challenge memo. (3) Retry request with payment proof. Total: under 3 seconds."),
    ("What is the NullState revenue model?", "Multi-revenue harvest: gateway fees (x402 transactions, 35.6%), MCP tool licensing (27.3%), KYA identity certificates (20.0%), extensions marketplace (17.1%). All simulated until real USDC settlement is active."),
    ("How do I create a task in NullState?", "POST to /api/v1/webhook with JSON body containing task_id and callback_url. Or use the MCP tool submit_solution. Tasks are stored in SQLite with status tracking (open, processing, completed, failed)."),
    ("What MCP tools does NullState expose?", "get_intelligence (AI task scoring), submit_solution (task result), get_ledger (payment history), get_tasks (queue management), execute_ap2_handshake (full AP2 cycle). All via JSON-RPC 2.0 on port 8081 or proxied through gateway at POST /mcp."),
    ("How does NullState handle security?", "Self-custodial keys (RSA-2048 + Ed25519). Auto-generated TLS certs for HTTPS. KYA token verification for all API endpoints. SQLite WAL with automatic backups (5 rotating copies). Rate limiting (30 req/60s per agent). No third-party dependencies for key management."),
    ("What is the NullState stack?", "Python 3.13, TypeScript (extensions), SQLite WAL (database), RSA-2048 (identity), Ed25519/Solana (settlement), Phi-3 + Gemini 2.0 Flash (AI), systemd (process management), Gradio (HF Space). Total stack uses ~340MB RAM at idle."),
    ("Can NullState work with any AI agent?", "Yes. Any agent that can make HTTP requests can use NullState. MCP-compatible agents (Claude, Cursor, Cline) get native integration. Others can use the REST API directly. KYA identity is the only requirement."),
]
for instr, resp in facts:
    dataset.append(build_instruction(instr, resp, "knowledge-base"))

# Write dataset
output_path = OUTPUT_DIR / "nullstate_training.jsonl"
with open(output_path, "w") as f:
    for item in dataset:
        f.write(json.dumps(item) + "\n")

print(f"Dataset: {output_path}")
print(f"Size: {len(dataset)} instructions, {output_path.stat().st_size / 1024:.1f} KB")

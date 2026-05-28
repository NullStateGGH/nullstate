"""Expand training dataset from production nullstate.db + Gemini synthesis.
Output: monetizable instruction dataset for agent-payment AI models."""

import json
import sqlite3
import os
import hashlib
import random
from datetime import datetime, timezone

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyB6PfFrxoam8LB7RJmVfra3Y-bWfqtzB6M")
DB_PATH = "src/core/nullstate.db"
OUTPUT_PATH = "src/training/nullstate_training_expanded.jsonl"
TEMPLATES_PATH = "src/training/generation_templates.json"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def task_to_instruction(task):
    """Convert a production task into an instruction/response pair."""
    keywords = json.loads(task["keywords"]) if isinstance(task["keywords"], str) else task["keywords"]
    weights = json.loads(task["weights"]) if isinstance(task["weights"], str) else task["weights"]
    kw_str = ", ".join(keywords) if keywords else "general"

    instructions = [
        {
            "instruction": f"Analyze this lead task from the NullState agent payment network: source={task['source']}, keywords={kw_str}, tier={task['tier']}. What is the optimal strategy for this task?",
            "response": f"This is a {task['tier']} tier task sourced from {task['source']} targeting keywords: {kw_str}. "
                       f"Weight distribution: {weights}. "
                       f"Recommended approach: assign SETTLEMENT priority with {task['settlement_currency']} settlement. "
                       f"Protocol: {task['payment_protocol']}. "
                       f"Status: {task['status']}. "
                       f"This task is suitable for autonomous agent processing via the NullState payment layer.",
            "domain": "task_analysis",
            "source": "production_task"
        },
        {
            "instruction": f"Generate an AI intent classification for a task with source={task['source']} and keywords={kw_str}. What type of agent activity does this represent?",
            "response": f"Task classification: {task['type']} with intent targeting {kw_str}. "
                       f"The source {task['source']} indicates {'API-based' if 'api' in str(task['source']).lower() else 'web-based' if 'http' in str(task['source']).lower() else 'repository'} activity. "
                       f"AUTO-CLASSIFY: This is a {task['tier']} intelligence-gathering operation suitable for the NullState agent swarm.",
            "domain": "intent_classification",
            "source": "production_task"
        },
    ]
    return instructions

def ledger_to_instruction(entry):
    """Convert a ledger entry into a training pair about payments."""
    instructions = [
        {
            "instruction": f"Explain this payment transaction on the NullState agent payment network: amount={entry['amount']} {entry['settlement_currency']}, protocol={entry['payment_protocol']}, source={entry['source']}",
            "response": f"Transaction of {entry['amount']} {entry['settlement_currency']} processed via {entry['payment_protocol']} protocol. "
                       f"Source: {entry['source']}. "
                       f"{'Verified on-chain' if entry['verified'] else 'Pending verification'}. "
                       f"Payment hash: {entry['transaction_hash'][:16]}... "
                       f"This represents an agent-to-agent payment settled through the NullState infrastructure.",
            "domain": "payment_analysis",
            "source": "production_ledger"
        },
        {
            "instruction": f"What does the x402 payment protocol look like in practice? Show a real transaction example.",
            "response": f"x402 Protocol Transaction Example:\n"
                       f"- Amount: {entry['amount']} {entry['settlement_currency']}\n"
                       f"- Source: {entry['source']}\n"
                       f"- Transaction Hash: {entry['transaction_hash'][:32]}...\n"
                       f"- Protocol: {entry['payment_protocol']}\n"
                       f"- Wallet: {entry['public_address'][:16]}...\n"
                       f"- Timestamp: {entry['timestamp']}\n"
                       f"This demonstrates HTTP 402 Payment Required semantics for machine-to-machine payments.",
            "domain": "x402_protocol",
            "source": "production_ledger"
        },
        {
            "instruction": f"How does the AP2 3-way handshake settle payments? Provide a real ledger example.",
            "response": f"AP2 Handshake Settlement Example:\n"
                       f"- Settlement: {entry['amount']} {entry['settlement_currency']}\n"
                       f"- Protocol: {entry['payment_protocol']}\n"
                       f"- Transaction: {entry['transaction_hash'][:32]}...\n"
                       f"- Payment Address: {entry['public_address'][:16]}...\n"
                       f"The AP2 protocol: (1) Checkout creates intent, (2) Charge executes payment, "
                       f"(3) Settlement confirms on-chain. This entry represents step 3 confirmation.",
            "domain": "ap2_protocol",
            "source": "production_ledger"
        },
    ]
    return instructions

def generate_synthetic_pairs():
    """Generate synthetic training pairs from protocol knowledge."""
    return [
        {
            "instruction": "What is the NullState x402 protocol and how does it work?",
            "response": "x402 is an HTTP 402 Payment Required protocol extension for AI agents. "
                       "When an agent requests a resource and lacks payment, the server returns HTTP 402 "
                       "with a Payment-Mint header. The agent constructs a payment, and upon verification, "
                       "the server releases the resource. This enables pay-per-use machine-to-machine "
                       "transactions without pre-existing contracts or API keys.",
            "domain": "x402_protocol",
            "source": "synthetic"
        },
        {
            "instruction": "Explain the AP2 3-way handshake protocol.",
            "response": "AP2 (Agent Payment Protocol v2) uses a 3-way handshake: "
                       "(1) POST /api/v1/ap2/checkout - Agent sends intent with caller_identity, "
                       "receives checkout_id and payment_details. "
                       "(2) POST /api/v1/ap2/charge - Agent sends signed mandate with checkout_id, "
                       "receives charge_id and transaction_hash. "
                       "(3) Settlement - Payment is verified on-chain and agent receives access. "
                       "All messages are RSA-2048 PKCS1v15-SHA256 signed using IntentMandate/CartMandate/PaymentMandate.",
            "domain": "ap2_protocol",
            "source": "synthetic"
        },
        {
            "instruction": "What is KYA (Know Your Agent) authentication?",
            "response": "KYA is NullState's agent identity verification protocol. Agents request a challenge "
                       "via GET /kya/challenge, receive a nonce, sign it with their RSA-2048 private key, "
                       "and receive a KYA token (1-hour TTL). The token is passed via X-KYA-Token header. "
                       "Rate limit: 30 requests per 60 seconds per agent. Enforced on POST /api/v1/ap2/* endpoints.",
            "domain": "kya_auth",
            "source": "synthetic"
        },
        {
            "instruction": "How does the NullState Protocol Shield normalize different protocol requests?",
            "response": "The Protocol Shield (ShieldedRequest + normalize()) auto-detects the protocol from incoming requests. "
                       "It checks: (1) Path patterns - /api/v1/ap2/* for AP2, /mcp for MCP, /kya/* for KYA, "
                       "llms.txt for discovery. (2) Headers - Payment-Mint for x402, X-KYA-Token for KYA, "
                       "Content-Type application/json for MCP. (3) Body content. Returns a normalized "
                       "ShieldedRequest with protocol, raw, headers, body fields.",
            "domain": "protocol_shield",
            "source": "synthetic"
        },
        {
            "instruction": "What is the difference between RSA-2048 and Solana Ed25519 wallets in NullState?",
            "response": "NullState maintains two wallet identities: (1) RSA-2048 keypair for AP2 mandate signing "
                       "and KYA challenge/response authentication - used for identity and message signing. "
                       "(2) Solana Ed25519 keypair for on-chain USDC settlement - used for actual fund transfers. "
                       "RSA handles authentication and intent, Solana handles settlement. Both private keys "
                       "are stored in src/wallet/.env with chmod 600.",
            "domain": "wallet_architecture",
            "source": "synthetic"
        },
        {
            "instruction": "How does NullState's dual-model AI integration work?",
            "response": "NullState uses a dual-model architecture: (1) Hugging Face Phi-3-mini-4k-instruct for "
                       "local inference - runs on CPU with 4K context window, handles basic intelligence tasks. "
                       "(2) Google Gemini 2.5 Flash API for advanced reasoning - handles complex analysis, "
                       "content generation, and telemetry scoring. Graceful degradation: if APIs are unreachable, "
                       "falls back to keyword-only responses. Telemetry scoring uses Gemini to evaluate "
                       "interaction quality on a 1-10 scale.",
            "domain": "ai_integration",
            "source": "synthetic"
        },
        {
            "instruction": "What revenue models does NullState support for agents?",
            "response": "NullState supports multiple revenue harvest models: (1) Per-task pricing: 0.025 USDC/task "
                       "via AP2 handshake. (2) x402 pay-per-resource: dynamic pricing based on intelligence value. "
                       "(3) Subscription tiers: Free (5 tasks/day), Pro ($9.99/mo, 500 tasks/day), "
                       "Enterprise (custom). (4) Dataset licensing: gated access to training data. "
                       "(5) Model inference API: per-token pricing for the NullState-specialized model. "
                       "All settlement in USDC on Solana.",
            "domain": "revenue_model",
            "source": "synthetic"
        },
        {
            "instruction": "How does NullState's self-improving feedback loop work?",
            "response": "The feedback loop: (1) Telemetry engine records every gateway interaction to SQLite "
                       "(telemetry.db). (2) Gemini 2.5 Flash scores interaction quality (1-10). "
                       "(3) High-quality interactions are extracted as training pairs. "
                       "(4) Training data is exported to GCS bucket weekly. "
                       "(5) Exported data feeds NullState model fine-tuning. "
                       "(6) Improved model drives better agent interactions. "
                       "This creates a flywheel: more usage -> more data -> better model -> more usage.",
            "domain": "feedback_loop",
            "source": "synthetic"
        },
        {
            "instruction": "What is the full NullState protocol stack?",
            "response": "NullState protocol stack (OSI-inspired): "
                       "Layer 7 - Application: AP2 (Agent Payment Protocol), x402 (HTTP 402), MCP (Model Context Protocol) "
                       "Layer 6 - Authentication: KYA (Know Your Agent), RSA-2048 challenge/response "
                       "Layer 5 - Session: 3-way handshake (checkout -> charge -> settle) "
                       "Layer 4 - Transport: JSON-RPC over HTTPS "
                       "Layer 3 - Network: Solana (for settlement), HTTP (for signaling) "
                       "Layer 2 - Security: RSA PKCS1v15-SHA256 signing, Ed25519 on-chain "
                       "Layer 1 - Settlement: USDC on Solana, fixed 0.025 USDC/task",
            "domain": "protocol_stack",
            "source": "synthetic"
        },
        {
            "instruction": "How do I integrate an AI agent with NullState for payments?",
            "response": "Integration steps: (1) Get a KYA token: POST to /kya/challenge, sign the nonce. "
                       "(2) Set up AP2 handshake: implement three calls - checkout, charge, settlement. "
                       "(3) For x402: handle HTTP 402 responses with Payment-Mint header, construct payment, retry. "
                       "(4) Use the MCP tools: execute_ap2_handshake, get_intelligence, submit_solution. "
                       "(5) Monitor via GET /health for task/ledger/balance status. "
                       "The NullState model provides intelligent routing for optimal protocol selection.",
            "domain": "integration_guide",
            "source": "synthetic"
        },
        {
            "instruction": "Explain NullState's approach to agent identity and reputation.",
            "response": "NullState uses KYA tokens for session identity (1-hour TTL). Agent reputation is built through: "
                       "(1) Task completion rate - ratio of completed vs assigned tasks. "
                       "(2) Payment history - on-time settlement via USDC. "
                       "(3) Quality scores from telemetry feedback loop (1-10). "
                       "(4) Protocol compliance - valid RSA signatures, proper handshake flow. "
                       "Reputation feeds into task routing: higher reputation agents get premium task assignments. "
                       "Rate limiting (30 req/60s) prevents abuse while allowing legitimate throughput.",
            "domain": "identity_reputation",
            "source": "synthetic"
        },
    ]

def build():
    db = get_db()
    tasks = db.execute("SELECT * FROM tasks").fetchall()
    ledger = db.execute("SELECT * FROM ledger").fetchall()
    
    all_pairs = []
    
    # Production task pairs
    for task in tasks:
        pairs = task_to_instruction(task)
        all_pairs.extend(pairs)
    
    # Production ledger pairs
    for entry in ledger:
        pairs = ledger_to_instruction(entry)
        all_pairs.extend(pairs)
    
    # Synthetic protocol knowledge pairs
    all_pairs.extend(generate_synthetic_pairs())
    
    # Write output
    with open("src/training/nullstate_training_expanded.jsonl", "w") as f:
        for pair in all_pairs:
            f.write(json.dumps(pair) + "\n")
    
    print(f"Generated {len(all_pairs)} training pairs:")
    domains = {}
    for p in all_pairs:
        d = p["domain"]
        domains[d] = domains.get(d, 0) + 1
    for d, c in sorted(domains.items(), key=lambda x: -x[1]):
        print(f"  {d}: {c}")
    print(f"Total size: {os.path.getsize('src/training/nullstate_training_expanded.jsonl') / 1024:.1f} KB")
    return all_pairs

if __name__ == "__main__":
    build()

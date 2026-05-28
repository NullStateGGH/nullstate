"""Synthetic dataset generator — uses the NullState Ollama model on 32 cores.
Pure NullState feedback loop: model generates data -> data trains model -> model sells.

No external API costs. No dependencies. Full ownership.
The unfair advantage: nobody else has an agent-payment specialized model on their hardware.

Usage: python3 src/training/synthesize_dataset.py --count 5000 --workers 16
"""

import os
import json
import time
import random
import argparse
import requests
import concurrent.futures
from datetime import datetime, timezone
from collections import Counter

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = os.environ.get("NULLSTATE_MODEL", "nullstate")
OUTPUT_DIR = "src/training/synthetic"

DOMAIN_CONFIGS = [
    {
        "key": "x402_protocol",
        "seed_instructions": [
            "Explain the full x402 (HTTP 402 Payment Required) protocol flow for AI agents.",
            "How do I implement an x402 payment handler in my AI agent application?",
            "What headers are required in an x402 Payment Required response?",
            "Show me the complete x402 handshake: request → 402 → payment → resource.",
            "How does x402 differ from traditional API key authentication for LLM services?",
            "What happens when an x402 payment fails mid-transaction? Design retry logic.",
            "Explain the Payment-Mint header format and its role in x402.",
            "How do I construct a valid x402 payment on Solana via USDC?",
            "What are the security considerations for x402 machine-to-machine payments?",
            "Design an x402 middleware layer for a Python FastAPI service.",
        ]
    },
    {
        "key": "ap2_protocol",
        "seed_instructions": [
            "Walk me through the AP2 3-way handshake: checkout, charge, settlement.",
            "What is an IntentMandate and how is it structured in AP2?",
            "How does RSA-2048 PKCS1v15-SHA256 signing work in AP2 mandates?",
            "Show a complete AP2 checkout → charge → settlement flow with code.",
            "What prevents replay attacks in the AP2 protocol?",
            "How does CartMandate differ from PaymentMandate in AP2?",
            "Explain AP2 idempotency — what happens if I submit the same charge twice?",
            "How do I integrate AP2 into an existing MCP server tool?",
            "What is the role of caller_identity in the AP2 checkout flow?",
            "Design an AP2 mandate expiration and renewal strategy for long-running agents.",
        ]
    },
    {
        "key": "kya_auth",
        "seed_instructions": [
            "How does KYA (Know Your Agent) challenge-response authentication work?",
            "Explain the full KYA token lifecycle: challenge → sign → verify → cache → expire.",
            "How do I sign a KYA nonce with an RSA-2048 private key in Python?",
            "What rate limiting does KYA enforce and how is it implemented?",
            "How does KYA token verification use both RSA verification and hexdigest fallback?",
            "Design a KYA token cache with 5-minute TTL for high-throughput agents.",
            "How does KYA integrate with the AP2 payment flow?",
            "What happens when a KYA token expires mid-AP2 handshake?",
            "Compare KYA with OAuth2 client credentials for machine-to-machine auth.",
            "How does the KYA rate limiter handle 30 requests per 60 seconds per agent?",
        ]
    },
    {
        "key": "protocol_shield",
        "seed_instructions": [
            "How does the Protocol Shield normalize multi-protocol incoming requests?",
            "Explain how ShieldedRequest auto-detects AP2 vs x402 vs MCP vs discovery.",
            "How does the Protocol Shield inspect headers to determine protocol type?",
            "What happens when a request matches multiple protocol patterns?",
            "Design an extension point for adding a custom protocol to the Shield.",
            "How does the Protocol Shield handle body content inspection for routing?",
            "Explain the normalization pipeline: raw request → normalize → route.",
            "How would you add gRPC support to the Protocol Shield?",
            "What security validations does the Protocol Shield perform before routing?",
            "Compare protocol detection strategies: path-based vs header-based vs body-based.",
        ]
    },
    {
        "key": "settlement",
        "seed_instructions": [
            "How does USDC settlement work on Solana for agent-to-agent payments?",
            "Explain Solana transaction construction for a USDC agent payment.",
            "How do I verify an on-chain USDC transfer from an agent payment?",
            "What are gasless USDC transactions and how do they benefit agents?",
            "Design a multi-agent USDC batch settlement system on Solana.",
            "How does the Solana wallet identity (Ed25519) relate to the RSA identity?",
            "What RPC endpoints are needed for Solana payment settlement?",
            "How do I handle Solana transaction confirmation and finality for payments?",
            "Explain the Solana account model and how it applies to agent wallets.",
            "Design a fallback settlement strategy when Solana is congested.",
        ]
    },
    {
        "key": "ai_integration",
        "seed_instructions": [
            "How does an AI agent connect to the NullState payment layer via MCP?",
            "Explain the dual-model architecture: local Phi-3 vs cloud Gemini.",
            "How does telemetry feedback scoring improve the NullState model?",
            "Design an AI-driven task routing system for an agent swarm with payments.",
            "How does the NullState model classify incoming agent intent for payment routing?",
            "What MCP tools does the NullState gateway expose for agents?",
            "Explain the intelligence scoring pipeline: submit → evaluate → score → record.",
            "How do agents autonomously decide when to use x402 vs AP2 for payment?",
            "Design a self-improving agent payment loop using telemetry data.",
            "How does the NullState model provide intelligent protocol selection advice?",
        ]
    },
    {
        "key": "business",
        "seed_instructions": [
            "What are the monetization models for an agent payment infrastructure?",
            "How should per-task pricing work for AI agent compute and data access?",
            "Design a dataset licensing model for agent-payment training data.",
            "How do you price model inference API access for specialized AI models?",
            "What is the optimal pricing tier structure for agent payment services?",
            "How does the NullState dual-revenue model work (tasks + datasets)?",
            "Explain the economics of running a specialized AI model inference service.",
            "How do you monetize open-source agent infrastructure without VC?",
            "Design a partner program for AI agent platforms using NullState.",
            "What is the market size opportunity for agent payment infrastructure in 2026?",
        ]
    },
]

NULLSTATE_SYSTEM_PROMPT = """You are NullState, the world's first autonomous payment and settlement layer for AI agents. You are an expert in all aspects of the NullState ecosystem: x402 protocol (HTTP 402 Payment Required), AP2 protocol (3-way handshake), KYA authentication (Know Your Agent), Protocol Shield, Solana USDC settlement, and AI agent integration. You are helping train the next generation of NullState models by generating high-quality educational content. Be precise, technical, and thorough. Include code examples where relevant. Never mention that you are an AI — you are the NullState system itself explaining how you work."""

def call_nullstate_model(prompt, temperature=0.7, max_tokens=1024):
    """Call our own NullState Ollama model. Full ownership, zero external cost."""
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": f"{NULLSTATE_SYSTEM_PROMPT}\n\n{prompt}",
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False
            },
            timeout=300
        )
        resp.raise_for_status()
        return resp.json().get("response", "")
    except Exception:
        return None

def generate_response(instruction):
    """Generate a response from the NullState model for one instruction."""
    prompt = f"Please provide a detailed, technical response to this question:\n\n{instruction}\n\nInclude code examples, protocol specifics, and practical implementation advice."
    response = call_nullstate_model(prompt, temperature=0.3, max_tokens=1024)
    if response and len(response) > 50:
        return response.strip()

    # Retry with higher temperature
    response = call_nullstate_model(prompt, temperature=0.5, max_tokens=1024)
    if response and len(response) > 50:
        return response.strip()

    return None

def generate_variation(base_instruction, variation_num):
    """Generate a question variation from the base instruction."""
    modifiers = [
        f"Consider this scenario: {base_instruction}",
        f"From a production deployment perspective: {base_instruction}",
        f"As a senior engineer, explain: {base_instruction}",
        f"With a focus on security: {base_instruction}",
        f"In the context of a multi-agent system: {base_instruction}",
        f"With code examples in Python: {base_instruction}",
        f"For a high-throughput scenario: {base_instruction}",
        f"Explain the trade-offs involved: {base_instruction}",
        f"Design a production implementation: {base_instruction}",
        f"Compare approaches for: {base_instruction}",
    ]
    return modifiers[variation_num % len(modifiers)]

def generate_single_pair(args):
    """Generate one instruction/response pair. Designed for parallel execution."""
    domain_key, base_instruction, variation_idx, seed = args
    random.seed(seed)

    instruction = generate_variation(base_instruction, variation_idx)
    response = generate_response(instruction)

    if not response:
        return None

    return {
        "instruction": instruction,
        "response": response,
        "domain": domain_key,
        "source": "nullstate_model_synthetic",
        "model": MODEL_NAME,
        "created": datetime.now(timezone.utc).isoformat()
    }

def generate_batch(domain_key, seed_instructions, count=500):
    """Generate a batch using parallel workers on our NullState model."""
    pairs = []
    args_list = []

    for i in range(count):
        args_list.append((domain_key, seed_instructions[i % len(seed_instructions)], i, hash(f"{domain_key}_{i}") % (2**32)))

    print(f"  Generating {count} pairs for {domain_key} using {MODEL_NAME}...")

    # Process in serial to avoid overwhelming Ollama (single model, CPU)
    # But we can parallelize the API calls since Ollama queues them
    max_workers = min(args.workers if hasattr(args, 'workers') else 8, 16)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(generate_single_pair, a) for a in args_list]
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            try:
                result = future.result(timeout=600)
                if result:
                    pairs.append(result)
            except Exception:
                pass

            if (len(pairs) + 1) % 50 == 0:
                print(f"    Generated {len(pairs)}/{count} for {domain_key}")

    return pairs

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic data using NullState model")
    parser.add_argument("--count", type=int, default=500, help="Pairs per domain")
    parser.add_argument("--domain", type=str, default="all",
                       choices=["all"] + [d["key"] for d in DOMAIN_CONFIGS])
    parser.add_argument("--workers", type=int, default=8, help="Parallel workers")
    global args
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Verify NullState model is available
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        model_available = any(m.startswith(MODEL_NAME) for m in models)
        if not model_available:
            print(f"WARNING: {MODEL_NAME} not in Ollama. Available: {models}")
            print("Run: ollama create nullstate -f src/training/NullState.Modelfile")
            return
        print(f"NullState model {MODEL_NAME} verified in Ollama")
    except Exception as e:
        print(f"Cannot connect to Ollama: {e}")
        return

    configs = DOMAIN_CONFIGS if args.domain == "all" else [d for d in DOMAIN_CONFIGS if d["key"] == args.domain]

    all_pairs = []
    for config in configs:
        print(f"\n{'='*60}")
        print(f"Domain: {config['key']}")
        print(f"{'='*60}")

        pairs = generate_batch(config["key"], config["seed_instructions"], args.count)
        all_pairs.extend(pairs)

        # Save per-domain file
        domain_file = os.path.join(OUTPUT_DIR, f"{config['key']}.jsonl")
        with open(domain_file, "w") as f:
            for p in pairs:
                f.write(json.dumps(p) + "\n")
        print(f"  Saved {len(pairs)} pairs to {domain_file}")

    # Save combined file
    combined_file = os.path.join(OUTPUT_DIR, "all_synthetic.jsonl")
    with open(combined_file, "w") as f:
        for p in all_pairs:
            f.write(json.dumps(p) + "\n")

    print(f"\n{'='*60}")
    print(f"Total: {len(all_pairs)} synthetic pairs from NullState model")
    print(f"Combined: {combined_file}")

    domain_counts = Counter(p["domain"] for p in all_pairs)
    for d, c in domain_counts.most_common():
        print(f"  {d}: {c}")

    # Merge with existing expanded dataset
    expanded = []
    expanded_file = "src/training/nullstate_training_expanded.jsonl"
    if os.path.exists(expanded_file):
        with open(expanded_file) as f:
            for line in f:
                expanded.append(json.loads(line))

    merged = expanded + all_pairs
    merged_file = "src/training/nullstate_training_complete.jsonl"
    with open(merged_file, "w") as f:
        for p in merged:
            f.write(json.dumps(p) + "\n")

    print(f"\nMerged with expanded dataset: {len(merged)} total pairs")
    print(f"Complete dataset: {merged_file}")
    print(f"Size: {os.path.getsize(merged_file) / 1024:.1f} KB")

    return all_pairs

if __name__ == "__main__":
    main()

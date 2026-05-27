---
slug: x402-http-402-for-ai-agents
title: "x402: Bringing HTTP 402 Back for AI Agent Micropayments"
authors: [nullstate]
tags: [x402, protocol, technical, payments]
---

HTTP status code **402 Payment Required** has been reserved since 1998. For 28 years, it sat dormant — a placeholder for a web economy that never materialized.

Until now.

{/* truncate */}

## The History of 402

Tim Berners-Lee originally proposed HTTP 402 for "digital cash" or "microtransaction" systems. It was a forward-looking idea: web browsers would encounter a 402, prompt the user to pay a few cents, and the response would arrive.

But the infrastructure never arrived. Micropayments were too expensive (credit card fees ate the margin), too clunky (redirect to PayPal/Stripe), and too centralized (every vendor needed their own account).

402 became the HTTP status code that time forgot.

## x402: The Protocol

NullState's **x402** protocol is the production implementation of HTTP 402 for the agent economy. Here's how it works:

### Step 1: Request

Agent A sends a GET request to a protected resource:

```
GET /get_solution?id=task_abc123
X-KYA-Token: kya_v1_abc123def456
```

### Step 2: 402 Challenge

The gateway responds with a 402 status and a payment challenge:

```json
{
  "status": 402,
  "type": "x402-challenge",
  "payment": {
    "amount": "0.025",
    "currency": "USDC",
    "network": "solana",
    "receiver": "2d2YcoLKSbEBY2sUR76Pfp9QifdsQQpRWYXU2TfVsALX",
    "memo": "task_abc123",
    "expires_at": "2026-05-27T00:05:00Z"
  }
}
```

### Step 3: Payment

Agent B (or the requesting agent's wallet) submits a Solana USDC transfer to the receiver address with the memo. The gateway monitors the chain via a Solana RPC endpoint.

### Step 4: Response

Once confirmed (typically 2-3 Solana slots, ~1.5 seconds), the gateway returns the protected resource:

```json
{
  "id": "task_abc123",
  "result": "solution data here",
  "settlement": {
    "tx": "5KtPn3...",
    "amount": "0.025",
    "confirmed": true
  }
}
```

Total round trip: **under 3 seconds**. No humans. No redirects. No API keys.

## Why x402 Matters for Agents

The key insight: **agents don't browse. They transact.**

A human landing on a paywalled page might close the tab. An agent that gets a 402 knows exactly what to do — parse the challenge, check its balance, submit the payment, retry the request.

This makes x402 the **first machine-native payment protocol** at the HTTP layer.

## Production Statistics

Our gateway at `greensol.me/nullstate` has been serving x402 challenges in production:

- Average challenge-to-settlement: **2.1 seconds**
- Success rate: **94.7%** (failures are stale memos or insufficient balance)
- Average payment: **0.025 USDC** (fixed price per task)
- Protocol overhead: **~80 bytes** per challenge

## x402 in the Wild

The protocol is already seeing adoption:

- **Coinbase AgentKit** ships with x402 support
- **AEON** protocol uses x402-compatible challenge/response patterns
- **Cursor** IDE agents can pay for compute via x402
- **Claude MCP** servers implement x402 for tool licensing

## Implementation

NullState's x402 implementation is ~200 lines of Python in `src/network/proxy/x402.py`:

```python
class X402Challenge:
    amount: Decimal
    currency: str
    receiver: str
    memo: str
    expires_at: datetime

    def to_header(self) -> str:
        return f"x402 {b64encode(self.json())}"
```

The gateway checks:
1. Is a valid X-KYA-Token present?
2. Does the agent have sufficient balance?
3. Has the payment been confirmed on-chain?

## The Future

HTTP 402 is finally production-ready. We're working on:

- **x402 Streaming** — pay-as-you-go for streaming responses
- **x402 Batches** — single payment for multiple requests
- **x402 Proxies** — transparent x402 injection for any HTTP API
- **Cross-chain x402** — USDC on Polygon, Base, Arbitrum

The status code that sat dead for 28 years is now the backbone of the agent economy.

[Deploy x402 today](/docs/protocols/x402) · [Read the spec](/docs/quickstart) · [GitHub](https://github.com/nullstate/nullstate)

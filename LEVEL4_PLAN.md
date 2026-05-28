# NullState — Level 4 Autonomous Deployment Plan

## Current State Assessment (Level 2.5)

### Running ✓
- 7 systemd services (gateway, MCP, mail, hub, github, model-api, daemon)
- HOD engine ($50/cycle simulated revenue)
- Autonomous cron: 9 jobs (backup, telemetry, content, P&L, self-heal, deployment)
- GCP telemetry (monitoring, logging)
- Website at greensol.me/nullstate/ with Docusaurus
- Mail server with Zoho SMTP relay + 1,890 emails archived
- Ollama inference (nullstate 9.6GB, llama3.1 4.9GB)
- 277 completed tasks, 449 ledger transactions

### Critical Gaps
| Gap | Impact | Severity |
|-----|--------|----------|
| **$0 real revenue** | Can't self-fund | CRITICAL |
| **Wallet $0 USDC** | No real payments flow | CRITICAL |
| **No paying customers** | Zero agent traffic | CRITICAL |
| **Health endpoint leaks** | Exposes wallet, IP, internals | HIGH |
| **No CI/CD** | Can't auto-deploy code changes | HIGH |
| **nullstate.io unregistered** | No brand domain | MEDIUM |
| **No real monetization** | x402/AP2 run but no one pays | CRITICAL |
| **No scaling logic** | Can't add resources on demand | MEDIUM |
| **No A/B testing** | Can't measure improvements | LOW |

---

## Level 4 Architecture

```
                      ┌─────────────────────────────┐
                      │     Level 4 Controller      │
                      │  (autonomous decision maker) │
                      └──────┬──────────┬───────────┘
                             │          │
              ┌──────────────▼──┐  ┌────▼──────────────┐
              │ Revenue Engine  │  │  Growth Engine    │
              │ (sells API,     │  │ (acquires agents, │
              │  processes      │  │  publishes        │
              │  payments)      │  │  content, SEO)    │
              └────────┬────────┘  └────────┬──────────┘
                       │                    │
              ┌────────▼────────────────────▼────────┐
              │           Core Infrastructure         │
              │  Gateway · MCP · Mail · Model · DB    │
              │  GCP Telemetry · Self-Heal · Backup   │
              └───────────────────────────────────────┘
```

### Key Principle: Revenue Must Be Real
The single metric that determines Level 4 achievement: **Real USDC revenue > Infrastructure costs**.

---

## Phase Roadmap

### Phase 1 — Fix the Leaks & Harden (Week 1)

**Goal**: Stop leaking info, secure the surface, make revenue possible.

1. **Sanitize health endpoint** — remove wallet address, internal IP, port layout
2. **Fund the wallet** — deposit real USDC to Solana wallet `2d2YcoLKSbEBY2sUR76Pfp9QifdsQQpRWYXU2TfVsALX` for gas/operations
3. **Set up devnet → mainnet switch** — wallet config for real vs test
4. **Add rate limiting & auth to model API** — prevent free-riding
5. **Fix broken footer links** — create extension doc stubs or remove
6. **Add .env validation** — fail fast if critical vars missing
7. **Patch HOD revenue to be real** — stop simulating $50, connect to actual API sales

### Phase 2 — Revenue Engine (Week 2)

**Goal**: Real money flows through the system.

1. **x402 payment processing** — wire up actual Solana USDC transfer verification
   - Create a real product/service agents can buy
   - Build payment verification webhook
   - Track settled payments in ledger
2. **AP2 mandate execution** — real RSA verification end-to-end
3. **Pricing API with real charges** — gateway charges real USDC for solutions
4. **Model API pay-per-token** — charge for inference via x402
5. **Mail server paid relay** — sell outbound email relay as a service
6. **Revenue dashboard** — real-time P&L in GCP Console

### Phase 3 — Growth Engine (Week 3)

**Goal**: Acquire agents/customers autonomously.

1. **Content pipeline** — HOD generates + publishes blog posts, SEO content
2. **Social presence** — auto-post to X (@NullState) with platform updates
3. **Directory listings** — submit to tool directories, AI agent marketplaces
4. **Referral/affiliate system** — agents refer other agents, earn USDC
5. **Public playground** — interactive demo at greensol.me/nullstate/playground
6. **Open-source engagement** — respond to GitHub issues, PRs, discussions
7. **LLM discovery optimization** — improve llms.txt, AI plugin manifest for LLM crawlers

### Phase 4 — Full Autonomy Loop (Week 4)

**Goal**: System runs itself with zero human intervention.

1. **Self-healing v2** — detect degraded performance, not just crashes
   - Response time monitoring → auto-restart if >5s
   - Disk monitoring → auto-clean logs/cache if >85%
   - Revenue monitoring → alert if revenue drops 50%+ in 24h
2. **Self-scaling** — if CPU/memory consistently >70%, provision more
   - GCP API to resize instance or add nodes
3. **Self-deploy** — git push → auto-build → auto-deploy (fix Cloud Build)
4. **Self-funding** — automatic cost optimization
   - Shut down non-revenue services during low-traffic hours
   - Negotiate spot instance pricing via GCP API
5. **Self-improving** — measure every change's impact on revenue
   - A/B test website changes
   - Track conversion from visitor → API call → payment
6. **Emergency mode** — if revenue < costs for 48h, auto-revert last changes

### Phase 5 — Domain & Brand (Ongoing)

1. **Register nullstate.io** — need registrar credentials
2. **Redirect greensol.me/nullstate → nullstate.io** when domain live
3. **Brand upgrade** — proper logo, social proof, case studies

---

## Architecture Changes Required

### Revenue Engine
```
Agent → POST /get_solution?id=task_X
          ├─ 402 → x402_challenge{amount, wallet, ref}
          ├─ Agent pays USDC to NullState wallet
          ├─ Agent POSTs /webhook/payment_settled{tx_hash}
          └─ Gateway verifies → streams solution
```

### HOD v2 — Real Revenue Tracking
```
Current: revenue += 50.0  # simulated
Target:  revenue = sum(settlements.amount WHERE verified=true)
         costs = sum(infra_costs + compute_costs)
         profit = revenue - costs
         if profit > 0: reinvest_in_growth()
         else: optimize_or_shrink()
```

### Self-Heal v2
```python
while True:
    for service in SERVICES:
        if not is_healthy(service):
            restart(service)
            log_incident()
    if revenue_24h < threshold:
        rollback_last_deploy()
        alert("revenue crash detected")
    if disk_usage > 85%:
        clean_logs()
        archive_old_data()
    sleep(60)
```

---

## Success Metrics (Level 4 Definition)

| Metric | Current | Level 4 Target |
|--------|---------|----------------|
| Real USDC revenue | $0 | >$100/month |
| Revenue > costs | No (simulated) | Yes (real) |
| Paying agents | 0 | >10 |
| Automated deploys | Manual FTP | Git push → auto |
| Self-heal coverage | Crash restart only | Performance + cost + security |
| Uptime | ~99% (no monitoring) | 99.9% (measured) |
| Content generation | 6 blog posts | Auto-published weekly |
| Domain | greensol.me/nullstate | nullstate.io |

---

## Key Decisions Needed

1. **How to fund initial wallet?** Deposit ~$50 USDC to Solana wallet for gas + first payouts
2. **What product/service to sell?** Model API inference? Solution lookup? Email relay?
3. **nullstate.io registrar?** Need credentials or access
4. **Cloud Build fix?** Need `iam.serviceAccounts.actAs` permission — founder action in GCP Console
5. **Revenue split?** What % goes to infrastructure vs founder vs reinvestment?

#!/bin/bash
# NullState Domain & Infrastructure Setup
# Early bird domain takeover — KPI #1
# Run: bash src/nullstate/training/domain_setup.sh

set -e

echo "=== NullState Domain & Infrastructure Setup ==="
echo ""

# ─── Domain Registration ──────────────────────────────────────────
# nullstate.io, nullstate.ai, nullstate.dev all available
# Register via Cloudflare, Namecheap, or Google Domains
# If founder has an account at any of these, use it.

echo "Domain Status (all available for registration):"
echo "  nullstate.io  — AVAILABLE (priority target)"
echo "  nullstate.ai  — AVAILABLE (brand alternative)"
echo "  nullstate.dev — AVAILABLE (developer audience)"
echo "  nullstate.app — AVAILABLE (trust signals)"
echo ""

# ─── DNS Configuration ───────────────────────────────────────────
# When domain is registered, set these records:

cat << 'DNSEOF'
DNS Records for nullstate.io:

A     @                  → <SERVER_IP>
AAAA  @                  → <SERVER_IPV6>
CNAME www               → greensol.me
CNAME gateway           → greensol.me
MX    @                  → mail.nullstate.io (priority 10)
TXT   @                  → "v=spf1 include:_spf.nullstate.io ~all"
TXT   @                  → "google-site-verification=<CODE>"
TXT   _dmarc             → "v=DMARC1; p=reject; rua=mailto:admin@nullstate.io"

Subdomains:
  A  mail               → <SERVER_IP>
  A  api                → <SERVER_IP>
  A  mcp                → <SERVER_IP>
  A  hub                → <SERVER_IP>
  A  model              → <SERVER_IP>
  CNAME docs            → greensol.me
  CNAME blog            → greensol.me
  CNAME www             → greensol.me

DNSEOF

# ─── Email Configuration ─────────────────────────────────────────
echo "Email Setup:"
echo "  SMTP server: localhost:2525 (NullState Mail Server)"
echo "  Admin email: admin@nullstate.io"
echo "  Mail queue: src/core/nullstate.db (mail_queue table)"
echo ""

# ─── SSL Certificates (Let's Encrypt) ────────────────────────────
echo "SSL Setup (when domain is live):"
echo "  sudo apt install certbot python3-certbot-nginx"
echo "  sudo certbot --nginx -d nullstate.io -d www.nullstate.io"
echo "  sudo certbot --nginx -d api.nullstate.io"
echo "  sudo certbot --nginx -d mail.nullstate.io"
echo ""

# ─── Social / Early Bird Presence ────────────────────────────────
echo "Early Bird Actions (KPI checklist):"
echo "  [ ] Register nullstate.io on Cloudflare/Namecheap"
echo "  [ ] Create Twitter/X: @nullstate_io"
echo "  [ ] Create LinkedIn: /company/nullstate"
echo "  [ ] Post on Hacker News: Show HN: NullState — Agent Payment Layer"
echo "  [ ] Submit to Product Hunt"
echo "  [ ] Add greensol.me/nullstate to Google Search Console"
echo "  [ ] Claim nullstate.io on Google Search Console"
echo "  [ ] Set up Cloudflare for nullstate.io"
echo ""

# ─── Test Current Infrastructure ─────────────────────────────────
echo "=== Infrastructure Status ==="

# Model API
if curl -sf http://localhost:8082/health > /dev/null 2>&1; then
    echo "  Model API (8082): RUNNING"
else
    echo "  Model API (8082): NOT RUNNING"
fi

# Gateway
if curl -sfk https://localhost:8080/health > /dev/null 2>&1; then
    echo "  Gateway (8080): RUNNING"
else
    echo "  Gateway (8080): NOT RUNNING"
fi

# Ollama
if systemctl is-active --quiet ollama.service; then
    echo "  Ollama: RUNNING"
else
    echo "  Ollama: NOT RUNNING"
fi

# HF Dataset
echo "  HF Dataset: https://huggingface.co/datasets/NullStateV1/nullstate-training-data"

echo ""
echo "=== Domain Setup Complete ==="

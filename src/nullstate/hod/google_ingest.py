"""Google SDK Knowledge Ingestion Pipeline.
Ingests Google API docs, SDK specs, and service knowledge into NullState training.
Feeds the NullState model with the entire Google ecosystem knowledge.

Unfair advantage: GCP service account + cloud-platform scope = absorb Google's entire API surface.
"""

import os
import json
import time
import requests
import logging
import sqlite3
import concurrent.futures
from datetime import datetime, timezone
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [GOOGLE_INGEST] %(message)s")
log = logging.getLogger("nullstate-google-ingest")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyB6PfFrxoam8LB7RJmVfra3Y-bWfqtzB6M")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
NULLSTATE_MODEL = os.environ.get("NULLSTATE_MODEL", "nullstate")
DB_PATH = "src/core/nullstate.db"

# Google API discovery document — the index of all Google APIs
GOOGLE_API_DISCOVERY = "https://www.googleapis.com/discovery/v1/apis"

# Target APIs most relevant to agent economy / enterprise
TARGET_API_PREFIXES = [
    "aiplatform", "gemini", "generativelanguage", "cloudai",
    "gmail", "calendar", "drive", "sheets", "docs", "slides",
    "cloudfunctions", "cloudrun", "appengine", "compute",
    "storage", "bigquery", "pubsub", "secretmanager",
    "iam", "cloudresourcemanager", "cloudkms",
    "dialogflow", "discoveryengine", "retail",
    "analytics", "searchconsole", "webmasters",
    "identitytoolkit", "cloudidentity",
]

# Enterprise/Fortune 500 integration patterns
ENTERPRISE_PATTERNS = [
    ("SAML SSO Integration", "How to integrate NullState with enterprise SAML SSO providers like Okta, Azure AD"),
    ("Enterprise Audit Logging", "Implementing SOC2-compliant audit trails for agent payment transactions"),
    ("RBAC Authorization", "Role-based access control for multi-tenant enterprise NullState deployments"),
    ("GDPR Compliance", "Data privacy compliance for agent payment data under GDPR regulations"),
    ("Fortune 500 Procurement", "Procurement-ready billing, invoicing, and vendor management patterns"),
    ("High Availability", "Multi-region HA deployment for enterprise-grade agent payment infrastructure"),
    ("Disaster Recovery", "DR planning and failover strategies for mission-critical payment systems"),
    ("Network Security", "VPC-SC, private endpoints, and zero-trust architecture for payment infrastructure"),
]


def get_gcp_token() -> Optional[str]:
    """Get GCP service account token."""
    try:
        r = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=5
        )
        return r.json().get("access_token") if r.status_code == 200 else None
    except Exception:
        return None


def discover_google_apis() -> List[Dict]:
    """Fetch Google API discovery document and extract relevant APIs."""
    try:
        r = requests.get(GOOGLE_API_DISCOVERY, timeout=15)
        if r.status_code != 200:
            log.warning(f"Discovery doc returned {r.status_code}")
            return []

        apis = r.json().get("items", [])
        relevant = []

        for api in apis:
            name = api.get("name", "")
            if any(prefix in name for prefix in TARGET_API_PREFIXES):
                relevant.append({
                    "name": name,
                    "version": api.get("version", ""),
                    "title": api.get("title", ""),
                    "description": api.get("description", ""),
                    "discovery_url": api.get("discoveryRestUrl", ""),
                    "documentation": api.get("documentationLink", ""),
                })

        log.info(f"Found {len(relevant)} relevant Google APIs out of {len(apis)} total")
        return relevant
    except Exception as e:
        log.error(f"Discovery failed: {e}")
        return []


def fetch_api_documentation(api: Dict) -> Optional[str]:
    """Fetch API documentation and summarize for training."""
    docs_url = api.get("documentation", "")
    discovery_url = api.get("discovery_url", "")

    if not docs_url and not discovery_url:
        return None

    # Try discovery doc first (machine-readable)
    if discovery_url:
        try:
            r = requests.get(discovery_url, timeout=15)
            if r.status_code == 200:
                doc = r.json()
                # Extract key information
                summary = {
                    "name": api["name"],
                    "version": api["version"],
                    "title": api["title"],
                    "description": api.get("description", ""),
                    "base_url": doc.get("baseUrl", ""),
                    "protocols": list(doc.get("protocols", {}).keys()) if doc.get("protocols") else [],
                    "api_endpoints": list(doc.get("resources", {}).keys())[:20] if doc.get("resources") else [],
                    "schemas": list(doc.get("schemas", {}).keys())[:30] if doc.get("schemas") else [],
                    "documentation_url": docs_url,
                }
                return json.dumps(summary)
        except Exception as e:
            log.debug(f"Discovery fetch failed for {api['name']}: {e}")

    return None


def generate_training_pairs_from_api(api_data: str, api_name: str) -> List[Dict]:
    """Use NullState model to generate instruction/response pairs from API knowledge."""
    try:
        prompt = f"""Convert this Google API specification into 3 instruction/response training pairs for an AI model that needs to understand how to use this API for agent payment systems.

API Specification: {api_data[:3000]}

Generate 3 pairs of {{"instruction": "question about using this API", "response": "detailed answer"}} focusing on how AI agents would use this API in conjunction with payment systems.
Return as JSON array."""

        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": NULLSTATE_MODEL, "prompt": prompt, "temperature": 0.3, "max_tokens": 2048, "stream": False},
            timeout=300
        )
        if resp.status_code == 200:
            result = resp.json().get("response", "")
            # Try to extract JSON array
            import re
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                pairs = json.loads(json_match.group())
                for p in pairs:
                    p["domain"] = f"google_{api_name}"
                    p["source"] = "google_api_ingest"
                return pairs
    except Exception as e:
        log.error(f"Training pair gen failed for {api_name}: {e}")

    return []


def generate_enterprise_patterns() -> List[Dict]:
    """Generate training pairs for enterprise/Fortune 500 integration patterns."""
    pairs = []
    for pattern_name, description in ENTERPRISE_PATTERNS:
        try:
            prompt = f"""Create an instruction/response training pair about: {description}

The response should be detailed, technical, and specific to how NullState implements this pattern.
Focus on enterprise requirements: security, compliance, audit, scalability."""

            resp = requests.post(
                f"{OLLAMA_HOST}/api/generate",
                json={"model": NULLSTATE_MODEL, "prompt": prompt, "temperature": 0.3, "max_tokens": 1024, "stream": False},
                timeout=300
            )
            if resp.status_code == 200:
                response_text = resp.json().get("response", "")
                if response_text and len(response_text) > 50:
                    pairs.append({
                        "instruction": f"How does NullState handle {pattern_name} for enterprise deployments?",
                        "response": response_text.strip(),
                        "domain": "enterprise_patterns",
                        "topic": pattern_name,
                        "source": "enterprise_ingest"
                    })
        except Exception as e:
            log.error(f"Enterprise pattern gen failed for {pattern_name}: {e}")

    return pairs


def fetch_google_trends_data() -> List[Dict]:
    """Fetch Google Trends data for agent economy market intelligence."""
    trends_queries = [
        "AI agent payments",
        "agent economy",
        "x402 protocol",
        "HTTP 402 payment",
        "AI agent infrastructure",
        "autonomous agent payments",
        "machine to machine payments",
        "AI API monetization",
        "crypto micropayments AI",
        "enterprise AI agents",
    ]

    pairs = []
    for query in trends_queries:
        try:
            # Use Gemini to analyze Google Trends data (simulated via Gemini knowledge)
            prompt = f"""Analyze the current market trend and trajectory for "{query}" in 2026.

Provide:
1. Current market state
2. Growth trajectory (1-2 year outlook)
3. Key players and competition
4. Revenue opportunity size
5. How NullState's agent payment infrastructure is positioned to capture this market

Focus on business intelligence, not technical details."""

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
            resp = requests.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800}
            }, timeout=30)

            if resp.status_code == 200:
                candidates = resp.json().get("candidates", [])
                if candidates:
                    text = candidates[0]["content"]["parts"][0]["text"]
                    pairs.append({
                        "instruction": f"What is the market opportunity for {query} and how is NullState positioned?",
                        "response": text.strip(),
                        "domain": "market_intelligence",
                        "topic": query,
                        "source": "google_trends_analysis",
                        "model": "gemini-2.0-flash"
                    })

            time.sleep(0.5)  # Rate limit
        except Exception as e:
            log.error(f"Trends analysis failed for {query}: {e}")

    return pairs


def store_training_pairs(pairs: List[Dict]):
    """Store generated training pairs to the training dataset."""
    if not pairs:
        return

    # Append to existing training data
    training_file = "src/training/nullstate_training_complete.jsonl"
    existing = []
    if os.path.exists(training_file):
        with open(training_file) as f:
            for line in f:
                existing.append(json.loads(line))

    all_pairs = existing + pairs

    with open(training_file, "w") as f:
        for p in all_pairs:
            f.write(json.dumps(p) + "\n")

    log.info(f"Stored {len(pairs)} new pairs (total: {len(all_pairs)})")


def run_ingestion_pipeline():
    """Run the complete Google SDK ingestion pipeline."""
    log.info("=" * 60)
    log.info("Google SDK Knowledge Ingestion Pipeline")
    log.info("=" * 60)

    all_pairs = []

    # Step 1: Discover Google APIs
    log.info("\nStep 1: Discovering Google APIs...")
    apis = discover_google_apis()
    log.info(f"  Found {len(apis)} relevant APIs")

    # Step 2: Fetch API documentation
    log.info("\nStep 2: Fetching API documentation...")
    api_docs = []
    for api in apis[:10]:  # Top 10 most relevant
        doc = fetch_api_documentation(api)
        if doc:
            api_docs.append((api["name"], doc))
            log.info(f"  Fetched: {api['name']} ({api['title']})")

    # Step 3: Generate training pairs from API knowledge
    log.info("\nStep 3: Generating training pairs from APIs...")
    for api_name, doc in api_docs:
        pairs = generate_training_pairs_from_api(doc, api_name)
        all_pairs.extend(pairs)
        log.info(f"  {api_name}: {len(pairs)} pairs")
        time.sleep(1)  # Space out model calls

    # Step 4: Generate enterprise pattern pairs
    log.info("\nStep 4: Generating enterprise/Fortune 500 patterns...")
    enterprise_pairs = generate_enterprise_patterns()
    all_pairs.extend(enterprise_pairs)
    log.info(f"  Enterprise patterns: {len(enterprise_pairs)} pairs")

    # Step 5: Market intelligence from Google Trends
    log.info("\nStep 5: Market intelligence from Google Trends...")
    trends_pairs = fetch_google_trends_data()
    all_pairs.extend(trends_pairs)
    log.info(f"  Market intelligence: {len(trends_pairs)} pairs")

    # Step 6: Store everything
    log.info("\nStep 6: Storing to training dataset...")
    store_training_pairs(all_pairs)

    log.info(f"\n{'='*60}")
    log.info(f"Ingestion complete: {len(all_pairs)} new training pairs")
    log.info(f"{'='*60}")

    return all_pairs


def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Google SDK Knowledge Ingestion")
    parser.add_argument("--apis-only", action="store_true", help="Only ingest API docs")
    parser.add_argument("--enterprise-only", action="store_true", help="Only generate enterprise patterns")
    parser.add_argument("--trends-only", action="store_true", help="Only fetch market intelligence")
    args = parser.parse_args()

    if args.apis_only:
        apis = discover_google_apis()
        docs = []
        for api in apis[:10]:
            doc = fetch_api_documentation(api)
            if doc:
                docs.append((api["name"], doc))
                print(f"{api['name']}: {api['title']}")
        print(f"\n{len(docs)} API docs fetched")
    elif args.enterprise_only:
        pairs = generate_enterprise_patterns()
        store_training_pairs(pairs)
        print(f"{len(pairs)} enterprise patterns generated")
    elif args.trends_only:
        pairs = fetch_google_trends_data()
        store_training_pairs(pairs)
        print(f"{len(pairs)} market intelligence pairs generated")
    else:
        run_ingestion_pipeline()


if __name__ == "__main__":
    main()

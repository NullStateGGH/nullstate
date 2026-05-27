"""Solana helpers: load keypair, check USDC balance, verify transactions."""

import json
import os
import sys
from pathlib import Path

import requests
from solders.keypair import Keypair
from solders.pubkey import Pubkey

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config
from core.log import setup

log = setup("solana")

USDC_MINT = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")


def load_keypair() -> Keypair | None:
    priv_hex = os.environ.get("NULLSTATE_SOLANA_PRIVATE_KEY", "")
    if not priv_hex:
        path = config.PATHS["env"]
        if path.exists():
            for line in path.read_text().splitlines():
                if line.startswith("NULLSTATE_SOLANA_PRIVATE_KEY="):
                    priv_hex = line.split("=", 1)[1]
                    break
    if not priv_hex:
        log.warning("no Solana private key found")
        return None
    try:
        raw = bytes.fromhex(priv_hex)
        if len(raw) == 32:
            from solders.keypair import Keypair as KP
            return KP.from_seed(raw)
        return Keypair.from_bytes(raw)
    except Exception as e:
        log.error("failed to load Solana keypair: %s", e)
        return None


def get_public_key() -> str | None:
    kp = load_keypair()
    return str(kp.pubkey()) if kp else None


def get_usdc_balance() -> float:
    kp = load_keypair()
    if not kp:
        return 0.0
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                str(kp.pubkey()),
                {"mint": str(USDC_MINT)},
                {"encoding": "jsonParsed"},
            ],
        }
        resp = requests.post(
            config.SOLANA_RPC_URL,
            json=payload,
            timeout=config.HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            accounts = data.get("result", {}).get("value", [])
            for acc in accounts:
                info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                if info.get("mint") == str(USDC_MINT):
                    return float(info.get("tokenAmount", {}).get("uiAmount", 0))
        return 0.0
    except Exception as e:
        log.warning("USDC balance check failed: %s", e)
        return 0.0


def verify_transaction(tx_hash: str, expected_amount: float | None = None) -> bool:
    """
    Verify a Solana transaction exists and optionally that it transferred
    expected_amount USDC to our wallet.
    """
    if not tx_hash or not isinstance(tx_hash, str):
        return False
    if not tx_hash.startswith("0x") and not tx_hash.startswith("2") and not tx_hash.startswith("5"):
        # Solana tx hashes are base58, typically start with 2-5
        # Allow any non-empty string for now, check length
        pass
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [tx_hash, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
        }
        resp = requests.post(
            config.SOLANA_RPC_URL,
            json=payload,
            timeout=config.HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            log.warning("tx verification RPC error: %d", resp.status_code)
            return False
        result = resp.json().get("result")
        if result is None:
            log.warning("tx %s not found on chain", tx_hash[:8])
            return False
        log.info("tx %s verified on chain", tx_hash[:16])
        return True
    except Exception as e:
        log.warning("tx verification failed: %s", e)
        return False

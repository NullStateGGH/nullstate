import json
import os
import hashlib
import hmac
import time
from pathlib import Path
from typing import Optional

KYA_TOKEN_TTL = 3600


def _get_private_key() -> Optional[str]:
    key = os.environ.get("NULLSTATE_WALLET_PRIVATE_KEY", "")
    if key and "BEGIN" in key and "END" in key:
        return key
    env_path = Path(__file__).resolve().parent.parent.parent / "wallet" / ".env"
    if not env_path.exists():
        return key or None
    lines = env_path.read_text().splitlines()
    capture = False
    parts = []
    for line in lines:
        if line.startswith("NULLSTATE_WALLET_PRIVATE_KEY="):
            eq = line.index("=")
            rest = line[eq + 1:].strip()
            if rest.startswith("-----"):
                capture = True
                parts.append(rest)
            elif capture:
                parts.append(line)
                if line.strip().endswith("KEY-----"):
                    break
            else:
                return rest
        elif capture:
            parts.append(line)
            if line.strip().endswith("KEY-----"):
                break
    if parts:
        return "\n".join(parts)
    return key or None


def _get_public_key() -> Optional[str]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    pem = _get_private_key()
    if not pem:
        return None
    try:
        key = serialization.load_pem_private_key(pem.encode(), password=None)
        pub = key.public_key()
        return pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
    except Exception:
        return None


def issue_challenge(agent_identity: str) -> dict:
    ts = int(time.time())
    raw = f"kya:challenge:{agent_identity}:{ts}"
    pem = _get_private_key()
    if pem:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        try:
            key = serialization.load_pem_private_key(pem.encode(), password=None)
            sig = key.sign(raw.encode(), padding.PKCS1v15(), hashes.SHA256())
            return {
                "kya_version": "1.0",
                "agent_identity": agent_identity,
                "challenge": raw,
                "signature": sig.hex(),
                "ttl": KYA_TOKEN_TTL,
                "ts": ts,
            }
        except Exception:
            digest = hashlib.sha256(raw.encode()).hexdigest()
            return {
                "kya_version": "1.0",
                "agent_identity": agent_identity,
                "challenge": raw,
                "signature": digest,
                "ttl": KYA_TOKEN_TTL,
                "ts": ts,
            }
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return {
        "kya_version": "1.0",
        "agent_identity": agent_identity,
        "challenge": raw,
        "signature": digest,
        "ttl": KYA_TOKEN_TTL,
        "ts": ts,
    }


def verify_agent(challenge: str, signature: str, agent_identity: str) -> bool:
    parts = challenge.split(":")
    if len(parts) >= 3 and parts[1] == "challenge":
        claimed_identity = parts[2]
        if claimed_identity != agent_identity:
            return False
    pem = _get_private_key()
    if pem and len(signature) == 512:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            key = serialization.load_pem_private_key(pem.encode(), password=None)
            sig_bytes = bytes.fromhex(signature)
            key.public_key().verify(sig_bytes, challenge.encode(), padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            return False
    expected = hashlib.sha256(challenge.encode()).hexdigest()
    return hmac.compare_digest(signature, expected)


_token_cache: dict[str, tuple[float, str]] = {}


def _cache_key(challenge: str, signature: str) -> str:
    return hashlib.sha256(f"{challenge}:{signature}".encode()).hexdigest()


def verify_token(token: str, agent_identity: str) -> bool:
    # Challenge format is "kya:challenge:<agent>:<ts>" — split at last colon
    # since signature is hex (no colons) and challenge contains colons.
    idx = token.rfind(":")
    if idx == -1:
        return False
    challenge = token[:idx]
    signature = token[idx + 1:]
    ck = _cache_key(challenge, signature)
    now = time.time()
    cached = _token_cache.get(ck)
    if cached:
        expiry, cached_agent = cached
        if now < expiry and cached_agent == agent_identity:
            return True
    if not verify_agent(challenge, signature, agent_identity):
        return False
    challenge_parts = challenge.split(":")
    if len(challenge_parts) >= 4 and challenge_parts[1] == "challenge":
        try:
            ts = float(challenge_parts[3])
            if now - ts > KYA_TOKEN_TTL:
                return False
        except (ValueError, IndexError):
            return False
    else:
        return False
    _token_cache[ck] = (now + min(KYA_TOKEN_TTL, 300), agent_identity)
    if len(_token_cache) > 1024:
        stale = [k for k, v in _token_cache.items() if v[0] < now]
        for k in stale:
            del _token_cache[k]
    return True

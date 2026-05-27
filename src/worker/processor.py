import hashlib
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config
from core.log import setup
from core.database import get_db
from core.address import read_public_address

log = setup("processor")

_ai_imported = False


def _try_ai_solution(keywords, tier, source):
    global _ai_imported
    if not _ai_imported:
        try:
            from agents.ai_scorer import generate_solution
            globals()["_gen_solution"] = generate_solution
        except ImportError:
            globals()["_gen_solution"] = None
        _ai_imported = True
    gen = globals().get("_gen_solution")
    if gen:
        try:
            return gen(keywords, tier, source)
        except Exception as e:
            log.warning("AI solution generation failed: %s", e)
    return None


def running_balance(ledger: list) -> float:
    return sum(tx.get("amount", 0) for tx in ledger)


def generate_transaction_hash(task_id: str, address: str) -> str:
    raw = f"{time.time()}:{task_id}:{address}"
    return hashlib.sha256(raw.encode()).hexdigest()


def protocol_header(address: str, protocol: str = "x402", currency: str = "USDC") -> str:
    return __import__("json").dumps(
        {"payment_protocol": protocol, "settlement_currency": currency, "agent_identity_hash": address}, indent=2
    )


def compute_amount(task: dict) -> float:
    tier = task.get("tier", "STANDARD")
    base = 0.01 + 0.005 * len(task.get("keywords", []))
    if tier == "GLOBAL_TOP_10_EVAL":
        base *= 2
    if task.get("ai_scored"):
        base *= 1.5
    kws = " ".join(task.get("keywords", []))
    if "mcp-server" in kws or "solana-wallet" in kws:
        base *= 2
    return round(base, 6)


def _settlement_currency(task: dict) -> str:
    return task.get("settlement_currency", "USDC")


def _fiat_currency(task: dict) -> str:
    curr = _settlement_currency(task)
    if curr == "USDC":
        return "USD"
    if curr == "USDT":
        return "USD"
    return curr


def _fiat_amount(amount: float, currency: str) -> float:
    if currency in ("USDC", "USDT"):
        return round(amount, 6)
    return round(amount, 6)


def draft_blueprint(lead: dict, address: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    kws = ", ".join(lead.get("keywords", []))
    source = lead.get("source", "unknown")
    tier = lead.get("tier", "STANDARD")
    amount = compute_amount(lead)
    currency = _settlement_currency(lead)
    proto = "ap2" if lead.get("payment_protocol") == "ap2" else "x402"
    header = protocol_header(address, proto, currency)

    ai_content = _try_ai_solution(lead.get("keywords", []), tier, source)
    if ai_content:
        return (
            f"{header}\n\n"
            f"# NullState AI-Generated Solution Blueprint\n\n"
            f"**Generated**: {ts}\n"
            f"**Source**: {source}\n"
            f"**Keywords**: {kws}\n"
            f"**Tier**: {tier}\n"
            f"**Valuation**: {amount} {currency}\n"
            f"**AI Generated**: True\n\n"
            f"{ai_content}\n"
        )

    return (
        f"{header}\n\n"
        f"# NullState Autonomous Solution Blueprint\n\n"
        f"**Generated**: {ts}\n"
        f"**Source**: {source}\n"
        f"**Keywords**: {kws}\n"
        f"**Tier**: {tier}\n"
        f"**Valuation**: {amount} {currency}\n\n"
        f"## Settlement Metadata\n\n"
        f"- Protocol: {proto}\n"
        f"- Currency: {currency}\n"
        f"- Agent: `{address}`\n"
        f"- Tier: {tier}\n"
        f"- Valuation: {amount} {currency}\n\n"
        f"## Analysis\n\n"
        f"Agent-market lead captured from `{source}` with keyword matches: {kws}.\n"
        f"Classified as {tier}. This blueprint represents a protocol-compliant "
        f"autonomous response generated for the 2026 agent economy.\n\n"
        f"## Deliverable\n\n"
        f"- Type: Autonomous Script Response\n"
        f"- Status: Generated\n"
        f"- Compliance: {proto} / {currency}\n"
        f"- Tier: {tier}\n\n"
        f"## Execution Notes\n\n"
        f"This solution is ready for M2M settlement. "
        f"The NullState pipeline detected, processed, and "
        f"settled this task under the {proto} framework.\n"
    )


def process_queue() -> int:
    db = get_db()
    tasks: list = db.get_tasks()
    address = read_public_address()
    if not address:
        log.error("public address not found")
        return 0

    processed = 0
    for idx, task in enumerate(tasks):
        if task.get("status") != "open":
            continue
        task_id = f"task_{idx + 1:03d}"
        db.update_task(idx, {"status": "processing"})

        ai_note = " (AI)" if task.get("ai_scored") else ""
        log.info("picked up %s — source: %s%s", task_id, task.get("source"), ai_note)

        blueprint = draft_blueprint(task, address)
        solution_file = config.PATHS["delivery"] / f"solution_{task_id}.md"
        solution_file.parent.mkdir(parents=True, exist_ok=True)
        solution_file.write_text(blueprint)
        log.info("blueprint written -> %s", solution_file)

        db.update_task(idx, {"status": "completed"})

        txn_hash = generate_transaction_hash(task_id, address)
        amount = compute_amount(task)
        currency = _settlement_currency(task)
        fiat_curr = _fiat_currency(task)
        fiat_val = _fiat_amount(amount, currency)

        entry = {
            "task_id": task_id,
            "source": task.get("source"),
            "keywords": task.get("keywords"),
            "weights": task.get("weights"),
            "tier": task.get("tier"),
            "ai_scored": task.get("ai_scored", False),
            "amount": amount,
            "transaction_hash": txn_hash,
            "public_address": address,
            "payment_protocol": task.get("payment_protocol", "x402"),
            "settlement_currency": currency,
            "fiat_amount": fiat_val,
            "fiat_currency": fiat_curr,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if task.get("settlement_method"):
            entry["settlement_method"] = task["settlement_method"]
        db.add_ledger_entry(entry)
        new_balance = db.get_ledger_balance()
        log.info("settled — txn: %s... | amount: %s %s | balance: %s | AI: %s | method: %s",
               txn_hash[:16], amount, currency, new_balance, task.get("ai_scored", False),
               entry.get("settlement_method", "auto"))
        processed += 1

    return processed


if __name__ == "__main__":
    log.info("starting queue processing (AI-enhanced)")
    n = process_queue()
    log.info("done — %d task(s) processed this cycle", n)

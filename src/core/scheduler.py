import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config
from core.log import setup
from core.store import atomic_read
from core.address import read_public_address

log = setup("scheduler")

_running = True


def _shutdown(signum, frame):
    global _running
    _running = False


def heartbeat_loop() -> None:
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    log.info("heartbeat started (interval=%ds)", config.HEARTBEAT_INTERVAL)

    while _running:
        tasks: list = atomic_read(config.PATHS["tasks"])
        address = read_public_address()
        if address:
            log.info("wallet OK — address: %s | tasks: %d pending", address, len(tasks))
        else:
            log.warning("wallet info missing")

        for _ in range(config.HEARTBEAT_INTERVAL):
            if not _running:
                break
            time.sleep(1)

    log.info("heartbeat stopped")


if __name__ == "__main__":
    heartbeat_loop()

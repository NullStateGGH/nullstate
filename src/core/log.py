import logging
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
LOG_DIR = BASE / "logs"
_root_configured = False


def setup(name: str, level: str = "INFO") -> logging.Logger:
    global _root_configured
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not _root_configured:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fmt = logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        )
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        fh = logging.FileHandler(LOG_DIR / "nullstate.log", encoding="utf-8")
        fh.setFormatter(fmt)
        logging.getLogger().addHandler(ch)
        logging.getLogger().addHandler(fh)
        _root_configured = True

    if not logger.handlers:
        logger.propagate = True

    return logger

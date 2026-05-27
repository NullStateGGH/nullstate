import fcntl
import json
import shutil
import tempfile
import time
from pathlib import Path

from . import config
from .log import setup

log = setup("store")

BACKUP_KEEP = 5


def atomic_write(path: Path, data: list | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup(path)
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        with open(fd, "w", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(json.dumps(data, indent=2))
            f.flush()
            os.fsync(fd)
            fcntl.flock(f, fcntl.LOCK_UN)
        shutil.move(tmp, path)
        tmp = None
    finally:
        if tmp and Path(tmp).exists():
            Path(tmp).unlink(missing_ok=True)


def atomic_read(path: Path) -> list | dict:
    if not path.exists():
        return _default(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        log.warning("corrupt state file %s — attempting backup recovery", path)
        recovered = _recover(path)
        if recovered is not None:
            return recovered
        bak = path.with_suffix(path.suffix + ".bak")
        if bak.exists():
            log.info("falling back to %s", bak)
            try:
                return json.loads(bak.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                pass
        log.error("unrecoverable state file %s — returning empty", path)
        return _default(path)


def _default(path: Path) -> list | dict:
    return [] if path.suffix == ".json" else {}


def _backup(path: Path) -> None:
    if not path.exists():
        return
    bak_dir = config.PATHS["backups"]
    bak_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    bak = bak_dir / f"{path.stem}_{ts}{path.suffix}"
    shutil.copy2(path, bak)
    existing = sorted(bak_dir.glob(f"{path.stem}_*{path.suffix}"))
    while len(existing) > BACKUP_KEEP:
        oldest = existing.pop(0)
        oldest.unlink()
        log.debug("pruned old backup %s", oldest.name)


def _recover(path: Path) -> list | dict | None:
    bak_dir = config.PATHS["backups"]
    snaps = sorted(bak_dir.glob(f"{path.stem}_*{path.suffix}"), reverse=True)
    for snap in snaps:
        try:
            data = json.loads(snap.read_text(encoding="utf-8"))
            log.info("recovered from backup %s", snap.name)
            return data
        except (json.JSONDecodeError, ValueError):
            continue
    return None


import os

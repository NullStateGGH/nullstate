import tempfile
from pathlib import Path
import pytest

from core.store import atomic_write, atomic_read


@pytest.fixture
def tmpfile():
    tmp = tempfile.mkstemp(suffix=".json")
    p = Path(tmp[1])
    yield p
    p.unlink(missing_ok=True)
    for bak in p.parent.glob(f"{p.stem}_*"):
        bak.unlink(missing_ok=True)


def test_write_and_read_list(tmpfile):
    data = [{"a": 1}, {"b": 2}]
    atomic_write(tmpfile, data)
    assert atomic_read(tmpfile) == data


def test_write_and_read_dict(tmpfile):
    data = {"key": "value", "num": 42}
    atomic_write(tmpfile, data)
    assert atomic_read(tmpfile) == data


def test_atomic_write_protects(tmpfile):
    data = [1, 2, 3]
    atomic_write(tmpfile, data)
    atomic_write(tmpfile, [4, 5])
    assert atomic_read(tmpfile) == [4, 5]


def test_read_nonexistent(tmpfile):
    nonexistent = tmpfile.parent / "no_such_file.json"
    assert atomic_read(nonexistent) == []


def test_atomic_backup_created(tmpfile):
    atomic_write(tmpfile, [1])
    atomic_write(tmpfile, [2])
    atomic_write(tmpfile, [3])
    atomic_write(tmpfile, [4])
    atomic_write(tmpfile, [5])
    atomic_write(tmpfile, [6])
    backups = list(tmpfile.parent.glob(f"{tmpfile.stem}_*"))
    assert len(backups) <= 5

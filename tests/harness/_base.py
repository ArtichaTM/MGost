from datetime import datetime, timezone
from hashlib import sha256
from os import stat_result, utime
from pathlib import Path
from tempfile import TemporaryDirectory

__all__ = ('FileStore', 'filler')


def filler(path: Path, size: int) -> bytes:
    """Deterministic content of exactly `size` bytes, unique per path.

    The old harness answered downloads with randbytes(), which makes any
    failure irreproducible. That matters because CI runs -n 2.
    """
    assert size >= 0
    if size == 0:
        return b''
    seed = sha256(path.as_posix().encode()).digest()
    return (seed * (size // len(seed) + 1))[:size]


class FileStore:
    """A real directory of files. Base for both sides of a sync."""

    __slots__ = ('_tmp', 'root')

    def __init__(self, prefix: str) -> None:
        self._tmp: TemporaryDirectory | None = TemporaryDirectory(
            prefix=prefix
        )
        self.root = Path(self._tmp.name).resolve()

    def _full(self, path: Path) -> Path:
        assert not path.is_absolute(), path
        return self.root / path

    def materialise(
        self,
        path: Path,
        size: int,
        modified: datetime,
    ) -> Path:
        return self.write(path, filler(path, size), modified)

    def write(
        self,
        path: Path,
        data: bytes,
        modified: datetime,
    ) -> Path:
        assert modified.tzinfo is not None, 'timestamps must be aware'
        full = self._full(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)
        stamp = modified.timestamp()
        utime(full, (stamp, stamp))
        return full

    def read(self, path: Path) -> bytes:
        return self._full(path).read_bytes()

    def paths(self) -> set[Path]:
        found: set[Path] = set()
        for directory, _, filenames in self.root.walk():
            for name in filenames:
                found.add((directory / name).relative_to(self.root))
        return found

    def stat(self, path: Path) -> stat_result:
        return self._full(path).lstat()

    def modified(self, path: Path) -> datetime:
        return datetime.fromtimestamp(
            self.stat(path).st_mtime, tz=timezone.utc
        )

    def exists(self, path: Path) -> bool:
        return self._full(path).is_file()

    def remove(self, path: Path) -> None:
        self._full(path).unlink()

    def move(self, src: Path, dst: Path) -> None:
        target = self._full(dst)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._full(src).rename(target)

    def close(self) -> None:
        """Idempotent. The old helper asserted its temp dir was not None
        on entry and nulled it on exit, so a double teardown raised."""
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None

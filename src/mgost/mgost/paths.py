"""Requirement paths sorted into ordinary and external files.

The server sends requirements root-relative, or absolute exactly as the
markdown wrote them. It stores both absolute paths and paths climbing out
with ``..`` as *fictional* files, keyed by the written string, so an
external file is always uploaded under ``written`` unchanged.
"""

from dataclasses import dataclass
from os.path import normpath
from pathlib import Path, PurePosixPath, PureWindowsPath

__all__ = ('External', 'classify')


@dataclass(frozen=True, slots=True)
class External:
    written: str
    "As the server sent it, and as it is uploaded"
    local: Path | None
    "None when written for another OS, so it can't exist here"


def _written_absolute(written: str) -> bool:
    return (
        PurePosixPath(written).is_absolute()
        or PureWindowsPath(written).is_absolute()
    )


def classify(root: Path, written: str) -> Path | External:
    """Root-relative `Path` for an ordinary file, `External` otherwise"""
    assert root.is_absolute()
    if _written_absolute(written):
        local = Path(written)
        return External(written, local if local.is_absolute() else None)
    # Lexical, as the server resolves it: a symlink can't change the kind
    local = Path(normpath(root / written))
    if not local.is_relative_to(root):
        return External(written, local)
    return local.relative_to(root)

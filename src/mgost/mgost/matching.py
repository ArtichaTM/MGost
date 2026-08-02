from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import file_digest as _hashlib_file_digest
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Collection

__all__ = (
    'Candidate', 'Match', 'Matcher', 'collect_candidates', 'file_digest'
)

logger = getLogger(__name__)

if TYPE_CHECKING:
    from mgost.api.schemas.mgost import ProjectFile


@dataclass(frozen=True, slots=True)
class Candidate:
    """A local file that no cloud file is known to occupy."""

    path: Path
    size: int
    modified: datetime


def file_digest(path: Path) -> str:
    """Lowercase hex SHA-256 of the file's raw bytes.

    Matches the server's definition exactly: no newline normalisation,
    no encoding step.
    """
    with path.open('rb') as file:
        return _hashlib_file_digest(file, 'sha256').hexdigest()


def collect_candidates(
    root: Path,
    tracked: Collection[Path],
) -> dict[Path, Candidate]:
    """Every local file that could be the new home of a cloud file.

    One walk for the whole sync, not one per missing file. Hidden
    directories are pruned in place: Path.walk is top-down and yields
    subdirectories regardless, so filtering on the yielded directory's
    own name lets .git/objects/ab/x through.
    """
    assert root.is_absolute()
    excluded = set(tracked)
    found: dict[Path, Candidate] = {}
    for directory, dirnames, filenames in root.walk():
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for name in filenames:
            full = directory / name
            relative = full.relative_to(root)
            if relative in excluded:
                continue
            stat = full.lstat()
            found[relative] = Candidate(
                path=relative,
                size=stat.st_size,
                modified=datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ),
            )
    return found


@dataclass(frozen=True, slots=True)
class Match:
    """A cloud file placed at a local path that is not where it was."""

    cloud_path: Path
    local_path: Path
    rung: int


class Matcher:
    """Resolves missing cloud files against unclaimed local files.

    Runs as passes over the whole set rather than an independent search
    per file, so two cloud files can never claim the same local file.
    """

    __slots__ = ('_root', '_candidates', '_claimed', '_digests')

    def __init__(
        self, root: Path, candidates: dict[Path, 'Candidate']
    ) -> None:
        assert root.is_absolute()
        self._root = root
        self._candidates = candidates
        self._claimed: set[Path] = set()
        self._digests: dict[Path, str] = {}

    def _digest(self, relative: Path) -> str:
        if relative not in self._digests:
            self._digests[relative] = file_digest(self._root / relative)
        return self._digests[relative]

    def _unclaimed(self) -> list['Candidate']:
        return [
            candidate
            for path, candidate in sorted(self._candidates.items())
            if path not in self._claimed
        ]

    def resolve(
        self, missing: dict[Path, 'ProjectFile']
    ) -> list[Match]:
        matches: list[Match] = []
        remaining = dict(sorted(missing.items()))
        self._pass_exact(remaining, matches)
        self._pass_name(remaining, matches)
        self._pass_remainder(remaining, matches)
        return matches

    def _pass_exact(
        self,
        remaining: dict[Path, 'ProjectFile'],
        matches: list[Match],
    ) -> None:
        for cloud_path in list(remaining):
            cloud_file = remaining[cloud_path]
            if cloud_file.size <= 0:
                # Every empty file shares a digest, so an empty file
                # carries no identity at all.
                continue
            pool = [
                c for c in self._unclaimed() if c.size == cloud_file.size
            ]
            # Deterministic regardless of filesystem order: a surviving
            # basename wins, then the sorted path.
            pool.sort(key=lambda c: (c.path.name != cloud_path.name, c.path))
            for candidate in pool:
                if self._digest(candidate.path) != cloud_file.hash:
                    continue
                logger.info(
                    f'"{cloud_path}" matched "{candidate.path}" by digest'
                )
                matches.append(Match(cloud_path, candidate.path, rung=1))
                self._claimed.add(candidate.path)
                del remaining[cloud_path]
                break

    def _pass_name(
        self,
        remaining: dict[Path, 'ProjectFile'],
        matches: list[Match],
    ) -> None:
        """The file was moved and edited, but kept its name.

        `name` is the final path component. A full-path match is
        impossible here: the caller only passes cloud files that have no
        local file at their own path.
        """
        for cloud_path in list(remaining):
            pool = [
                c for c in self._unclaimed()
                if c.path.name == cloud_path.name
            ]
            if len(pool) != 1:
                continue
            candidate = pool[0]
            logger.info(
                f'"{cloud_path}" matched "{candidate.path}" by name'
            )
            matches.append(Match(cloud_path, candidate.path, rung=2))
            self._claimed.add(candidate.path)
            del remaining[cloud_path]

    def _pass_remainder(
        self,
        remaining: dict[Path, 'ProjectFile'],
        matches: list[Match],
    ) -> None:
        """Name, mtime and content all changed — arity is the only
        evidence left, so require exactly one of each."""
        pool = self._unclaimed()
        if len(remaining) != 1 or len(pool) != 1:
            return
        cloud_path = next(iter(remaining))
        cloud_file = remaining[cloud_path]
        candidate = pool[0]
        if candidate.size == cloud_file.size:
            # Equal size already went through pass 1's hash check and
            # failed it — that is stronger, negative evidence which a
            # weaker arity-only pass must not override.
            return
        logger.info(
            f'"{cloud_path}" matched "{candidate.path}" as sole remainder'
        )
        matches.append(Match(cloud_path, candidate.path, rung=3))
        self._claimed.add(candidate.path)
        del remaining[cloud_path]

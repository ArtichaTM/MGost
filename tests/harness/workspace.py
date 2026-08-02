from datetime import datetime
from pathlib import Path

from ._base import FileStore

__all__ = ('Workspace', )


class Workspace(FileStore):
    """The local project directory."""

    __slots__ = ()

    EXCLUDED = '.mgost'

    def copy_from_cloud(
        self,
        cloud: FileStore,
        cloud_path: Path,
        local_path: Path,
        modified: datetime,
    ) -> Path:
        """Place the cloud file's exact bytes at a new local path.

        `filler()` seeds content from the path, so `materialise` at a new
        path yields different bytes and cannot express a move.
        """
        return self.write(local_path, cloud.read(cloud_path), modified)

    def paths(self) -> set[Path]:
        """Everything except the .mgost directory.

        Prunes the directory rather than skipping by name, so nested
        paths under .mgost cannot leak into convergence checks.
        """
        found: set[Path] = set()
        for directory, dirnames, filenames in self.root.walk():
            if self.EXCLUDED in dirnames:
                dirnames.remove(self.EXCLUDED)
            for name in filenames:
                found.add((directory / name).relative_to(self.root))
        return found

    def assert_converged(self, cloud: FileStore) -> None:
        """Local tree matches the cloud on paths, sizes and mtimes.

        Deliberately does NOT compare content: sync does nothing when
        |dmtime| < 1s, so two sides seeded with different bytes at the
        same mtime are converged by design, and asserting content would
        manufacture failures that are not bugs.
        """
        local = self.paths()
        remote = cloud.paths()
        assert local == remote, (
            'Path sets differ.'
            f'\n  only local: {sorted(p.as_posix() for p in local - remote)}'
            f'\n  only cloud: {sorted(p.as_posix() for p in remote - local)}'
        )
        for path in sorted(local):
            name = path.as_posix()
            local_size = self.stat(path).st_size
            cloud_size = cloud.stat(path).st_size
            assert local_size == cloud_size, (
                f'size differs for {name}: '
                f'{local_size} local vs {cloud_size} cloud'
            )
            assert self.modified(path) == cloud.modified(path), (
                f'mtime differs for {name}: '
                f'{self.modified(path)} local vs '
                f'{cloud.modified(path)} cloud'
            )

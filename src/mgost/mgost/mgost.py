from pathlib import Path

from mgost.settings import MGostInfo


class MGost:
    __slots__ = (
        '_root_path',
        '_info',
    )
    _root_path: Path
    _info: MGostInfo | None

    def __init__(
        self,
        root_path: Path
    ) -> None:
        self._root_path = root_path
        self._info = None

    def __enter__[T: MGost](self: T) -> T:
        assert self._info is None
        self._info = MGostInfo.load(self._root_path / '.mgost')
        return self

    def __exit__(self, *_):
        assert self._info is not None
        self._info.save(self._root_path / '.mgost')

    @property
    def info(self) -> MGostInfo:
        assert self._info is not None, "MGost should be"\
            " initialized as context manager"
        return self._info

    def build(self) -> None:
        print('BUILD!')

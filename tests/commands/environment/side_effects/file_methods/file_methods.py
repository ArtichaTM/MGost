from typing import TYPE_CHECKING, Callable

from httpx import Request, Response

from .base import FileMethodsBase
from .existing import ExistingFileMethods
from .new import NewFileMethods

if TYPE_CHECKING:
    from ...helper import EnvironmentHelper


class FileMethods:
    __slots__ = (
        'existing',
        'new'
    )
    existing: ExistingFileMethods
    new: NewFileMethods

    def __init__(
        self,
        env: 'EnvironmentHelper'
    ) -> None:
        self.existing = ExistingFileMethods(env)
        self.new = NewFileMethods(env)

    def get_side_effect(
        self,
        type: str,
        method: str
    ) -> Callable[[Request], Response]:
        type_method = getattr(self, type, None)
        assert type_method is not None, type
        assert isinstance(type_method, FileMethodsBase)
        return type_method.get_side_effect(method)

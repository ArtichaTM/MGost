from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

from httpx import Request, Response

if TYPE_CHECKING:
    from ...helper import EnvironmentHelper


class FileMethodsBase(ABC):
    __slots__ = ('env', )
    env: 'EnvironmentHelper'

    def __init__(
        self,
        env: 'EnvironmentHelper'
    ) -> None:
        super().__init__()
        self.env = env

    @abstractmethod
    async def put(self, request: Request) -> Response:
        raise NotImplementedError()

    @abstractmethod
    async def post(self, request: Request) -> Response:
        raise NotImplementedError()

    @abstractmethod
    async def patch(self, request: Request) -> Response:
        raise NotImplementedError()

    @abstractmethod
    async def delete(self, request: Request) -> Response:
        raise NotImplementedError()

    @abstractmethod
    async def get(self, request: Request) -> Response:
        raise NotImplementedError()

    def get_side_effect(
        self, method: str
    ) -> Callable[[Request], Response]:
        assert isinstance(method, str)
        func = getattr(self, method, None)
        assert func is not None
        return func

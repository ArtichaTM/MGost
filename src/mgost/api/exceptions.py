from httpx import Response


class WrongToken(Exception):
    pass


class ClientClosed(Exception):
    pass


class APIRequestError(Exception):
    __slots__ = (
        'response',
        'detail',
    )
    response: Response
    detail_: str

    def __init__(
        self,
        response: Response,
        detail: str
    ) -> None:
        super().__init__()
        assert isinstance(response, Response)
        assert isinstance(detail, str)
        self.response = response
        self.detail = detail

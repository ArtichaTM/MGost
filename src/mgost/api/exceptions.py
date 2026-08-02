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


UPLOAD_ERRORS = {
    409: 'файл с таким путём уже существует в облаке',
    404: 'файл не найден в облаке',
    413: 'файл больше 20 МБ',
}


def upload_error_message(status_code: int) -> str:
    return UPLOAD_ERRORS.get(
        status_code, f'ошибка загрузки №{status_code}'
    )

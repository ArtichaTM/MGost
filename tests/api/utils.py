from mgost.api import ArtichaAPI

from ..utils import API_TOKEN, BASE_URL


def init_api(token: str | None = None) -> ArtichaAPI:
    if token is None:
        token = API_TOKEN
    return ArtichaAPI(
        token,
        base_url=BASE_URL
    )

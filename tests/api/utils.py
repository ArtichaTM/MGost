from random import shuffle
from string import ascii_letters

from mgost.api import ArtichaAPI

BASE_URL = "https://api.example.com"
letters = [*ascii_letters]
shuffle(letters)
API_TOKEN = ''.join(letters)
del letters


def init_api(token: str | None = None) -> ArtichaAPI:
    if token is None:
        token = API_TOKEN
    return ArtichaAPI(
        token,
        base_url=BASE_URL
    )

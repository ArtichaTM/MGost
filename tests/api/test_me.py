from datetime import datetime, timedelta
from random import shuffle
from string import ascii_letters

import httpx
import pytest
import respx

from mgost.api import ArtichaAPI
from mgost.api.schemas.general import TokenInfo
from mgost.api.schemas.mgost import ErrorMessage

BASE_URL = "https://api.example.com"
letters = [*ascii_letters]
shuffle(letters)
API_TOKEN = ''.join(letters)
del letters


def _init_api(token: str | None = None) -> ArtichaAPI:
    if token is None:
        token = API_TOKEN
    return ArtichaAPI(
        token,
        base_url=BASE_URL
    )


@pytest.mark.asyncio
async def test_me_correct(respx_mock: respx.MockRouter):
    token = API_TOKEN
    mock_token_info = TokenInfo(
        name='Test',
        owner='TestOwner',
        created=datetime.now() - timedelta(minutes=60),
        modified=datetime.now() - timedelta(minutes=30)
    )
    route = respx_mock.get(
        f"{BASE_URL}/me", headers={'X-API-Key': token}
    ).respond(
        200, json=mock_token_info.model_dump(mode='json')
    )

    api = _init_api(token=token)
    async with api:
        token_info = await api.me()

    assert mock_token_info == token_info

    assert route.called
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_me_incorrect_token(respx_mock):
    token = [*API_TOKEN]
    shuffle(token)
    token = ''.join(token)
    route = respx_mock.get(
        f"{BASE_URL}/me", headers={'X-API-Key': token}
    ).respond(
        403, json=ErrorMessage(
            message='API key is incorrect', code=403
        ).model_dump(mode='json')
    )

    api = _init_api(token=token)
    e = None
    try:
        async with api:
            await api.me()
    except httpx.HTTPStatusError as _e:
        e = _e
    assert e is not None

    assert route.called
    assert route.call_count == 1

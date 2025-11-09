from datetime import datetime, timedelta
from random import shuffle

import httpx
import pytest
import respx

from mgost.api.schemas.general import TokenInfo
from mgost.api.schemas.mgost import ErrorMessage

from .utils import API_TOKEN, BASE_URL, init_api


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

    api = init_api(token=token)
    async with api:
        token_info = await api.me()

    assert route.called
    assert route.call_count == 1

    assert mock_token_info == token_info


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

    api = init_api(token=token)
    try:
        async with api:
            await api.me()
    except httpx.HTTPStatusError:
        pass
    else:
        raise AssertionError

    assert route.called
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_me_incorrect_length(respx_mock):
    token = API_TOKEN[:-1]
    route = respx_mock.get(
        f"{BASE_URL}/me", headers={'X-API-Key': token}
    ).respond(
        400, json=ErrorMessage(
            message='API key should be exactly 64 symbols', code=400
        ).model_dump(mode='json')
    )

    api = init_api(token=token)
    try:
        async with api:
            await api.me()
    except httpx.HTTPStatusError:
        pass
    else:
        raise AssertionError

    assert route.called
    assert route.call_count == 1

from datetime import datetime, timezone

import httpx
import pytest
import respx

from mgost.api import ArtichaAPI
from mgost.api.schemas.general import TokenInfo
from mgost.api.schemas.mgost import ErrorMessage
from tests.harness import BASE_URL

TOKEN = 'a' * 64


@pytest.fixture
async def api():
    async with ArtichaAPI(TOKEN, base_url=BASE_URL) as client:
        yield client


async def test_me_returns_token_info(respx_mock: respx.MockRouter, api):
    expected = TokenInfo(
        name='Test', owner='TestOwner',
        created=datetime.now(timezone.utc),
        modified=datetime.now(timezone.utc),
    )
    route = respx_mock.get(
        f'{BASE_URL}/me', headers={'X-API-Key': TOKEN},
    ).respond(200, json=expected.model_dump(mode='json'))

    assert await api.me() == expected
    assert route.call_count == 1


@pytest.mark.parametrize(
    'status, message',
    [
        (403, 'API key is incorrect'),
        (400, 'API key should be exactly 64 symbols'),
        (500, 'Internal server error'),
    ],
    ids=['forbidden', 'bad-length', 'server-error'],
)
async def test_me_raises_on_error_status(
    respx_mock: respx.MockRouter, api, status, message
):
    route = respx_mock.get(f'{BASE_URL}/me').respond(
        status,
        json=ErrorMessage(message=message, code=status).model_dump(
            mode='json'
        ),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await api.me()
    assert route.call_count == 1


async def test_trust(respx_mock: respx.MockRouter, api):
    respx_mock.get(f'{BASE_URL}/trust').respond(200, json={'trust': 1})
    result = await api.trust()
    assert result == 1
    assert isinstance(result, int)


async def test_trust_factors(respx_mock: respx.MockRouter, api):
    expected = {'Value1': 1, 'Value2': 2}
    respx_mock.get(f'{BASE_URL}/trust/factors').respond(200, json=expected)
    assert await api.trust_factors() == expected

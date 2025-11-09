import pytest
import respx

from .utils import API_TOKEN, BASE_URL, init_api


@pytest.mark.asyncio
async def test_trust_factors_correct(respx_mock: respx.MockRouter):
    token = API_TOKEN
    mock_trust = {'trust': 1}
    route = respx_mock.get(
        f"{BASE_URL}/trust", headers={'X-API-Key': token}
    ).respond(
        200, json=mock_trust
    )

    api = init_api(token=token)
    async with api:
        trust = await api.trust()

    assert route.called
    assert route.call_count == 1

    assert type(mock_trust['trust']) is type(trust)
    assert mock_trust['trust'] == trust

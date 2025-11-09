import pytest
import respx

from .utils import API_TOKEN, BASE_URL, init_api


@pytest.mark.asyncio
async def test_trust_factors_correct(respx_mock: respx.MockRouter):
    token = API_TOKEN
    mock_trust_factors = {
        'Value1': 1,
        'Value2': 2
    }
    route = respx_mock.get(
        f"{BASE_URL}/trust/factors", headers={'X-API-Key': token}
    ).respond(
        200, json=mock_trust_factors
    )

    api = init_api(token=token)
    async with api:
        trust_factors = await api.trust_factors()

    assert route.called
    assert route.call_count == 1

    assert mock_trust_factors == trust_factors

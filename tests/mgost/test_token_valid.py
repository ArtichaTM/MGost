from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from mgost.api import ArtichaAPI
from mgost.api.schemas import TokenInfo
from mgost.console import Console
from mgost.mgost.utils import token_valid
from mgost.settings import ApiKeyHolder
from tests.harness import BASE_URL

TYPED = 'typed'


def _me(request: httpx.Request) -> httpx.Response:
    if request.headers['X-API-Key'] != TYPED:
        return httpx.Response(403, json={'detail': 'API key is incorrect'})
    now = datetime.now(UTC)
    info = TokenInfo(name='t', owner='o', created=now, modified=now)
    return httpx.Response(200, json=info.model_dump(mode='json'))


async def test_typed_token_replaces_rejected(
    respx_mock: respx.MockRouter, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        type(Console), 'prompt', lambda self, *a, **kw: TYPED
    )
    me = respx_mock.get(f'{BASE_URL}/me').mock(side_effect=_me)
    api_key = ApiKeyHolder(tmp_path / '.env')

    async with ArtichaAPI(api_key.api_key) as api:
        assert await token_valid(api, api_key)

    assert me.call_count == 2
    assert me.calls.last.request.headers['X-API-Key'] == TYPED

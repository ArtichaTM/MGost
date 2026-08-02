from pathlib import Path

import httpx
import pytest
import respx

from mgost.api import ArtichaAPI
from tests.harness import BASE_URL


@pytest.fixture
async def api():
    async with ArtichaAPI('token', base_url=BASE_URL) as client:
        yield client


@pytest.mark.parametrize(
    'status, detail',
    [
        (409, 'ProjectFile with this path already exists'),
        (413, 'File too large'),
        (500, 'Internal server error'),
    ],
    ids=['conflict', 'too-large', 'server-error'],
)
async def test_failed_upload_raises(
    respx_mock: respx.MockRouter, api, workspace, clock, status, detail
):
    path = Path('main.md')
    workspace.materialise(path, size=20, modified=clock.second_ago)
    respx_mock.post(
        f'{BASE_URL}/mgost/project/1/files/main.md'
    ).respond(status, json={'detail': detail})

    with pytest.raises(httpx.HTTPStatusError):
        await api.upload(1, workspace.root, path, overwrite=False)


async def test_failed_overwrite_raises(
    respx_mock: respx.MockRouter, api, workspace, clock
):
    path = Path('main.md')
    workspace.materialise(path, size=20, modified=clock.second_ago)
    respx_mock.put(
        f'{BASE_URL}/mgost/project/1/files/main.md'
    ).respond(404, json={'detail': 'ProjectFile not found'})

    with pytest.raises(httpx.HTTPStatusError):
        await api.upload(1, workspace.root, path, overwrite=True)


async def test_every_request_carries_lang(cloud, api):
    await api.me()
    request = cloud.router.calls.last.request
    assert request.url.params.get('lang') == 'ru'

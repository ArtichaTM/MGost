from pathlib import Path

import httpx
import pytest
import respx

from mgost.api import ArtichaAPI
from tests.harness import BASE_URL

CONFLICT = 'ProjectFile with this path already exists'


@pytest.fixture
async def api():
    async with ArtichaAPI('token', base_url=BASE_URL) as client:
        yield client


@pytest.mark.parametrize(
    'status, detail',
    [
        (413, 'File too large'),
        (500, 'Internal server error'),
    ],
    ids=['too-large', 'server-error'],
)
async def test_failed_upload_raises(
    respx_mock: respx.MockRouter, api, workspace, clock, status, detail
):
    path = Path('main.md')
    workspace.materialise(path, size=20, modified=clock.second_ago)
    respx_mock.post(
        f'{BASE_URL}/mgost/project/1/files', params={'path': 'main.md'}
    ).respond(status, json={'detail': detail})

    with pytest.raises(httpx.HTTPStatusError):
        await api.upload(1, workspace.root / path, 'main.md', None)


async def test_conflict_with_unlisted_file_raises(
    respx_mock: respx.MockRouter, api, workspace, clock
):
    path = Path('main.md')
    workspace.materialise(path, size=20, modified=clock.second_ago)
    respx_mock.post(
        f'{BASE_URL}/mgost/project/1/files', params={'path': 'main.md'}
    ).respond(409, json={'detail': CONFLICT})
    respx_mock.get(f'{BASE_URL}/mgost/project/1/files').respond(200, json=[])

    with pytest.raises(httpx.HTTPStatusError):
        await api.upload(1, workspace.root / path, 'main.md', None)


async def test_conflict_overwrites_existing_file(
    respx_mock: respx.MockRouter, api, workspace, clock
):
    path = Path('main.md')
    workspace.materialise(path, size=20, modified=clock.second_ago)
    respx_mock.post(
        f'{BASE_URL}/mgost/project/1/files', params={'path': 'main.md'}
    ).respond(409, json={'detail': CONFLICT})
    respx_mock.get(f'{BASE_URL}/mgost/project/1/files').respond(200, json=[{
        'id': 7, 'project_id': 1, 'path': 'main.md', 'fictional': False,
        'created': clock.second_ago.isoformat(),
        'modified': clock.second_ago.isoformat(),
        'size': 20, 'hash': '0' * 64,
    }])
    put = respx_mock.put(f'{BASE_URL}/mgost/project/1/files/7').respond(200)

    await api.upload(1, workspace.root / path, 'main.md', None)

    assert put.called


async def test_failed_overwrite_raises(
    respx_mock: respx.MockRouter, api, workspace, clock
):
    path = Path('main.md')
    workspace.materialise(path, size=20, modified=clock.second_ago)
    respx_mock.put(
        f'{BASE_URL}/mgost/project/1/files/7'
    ).respond(404, json={'detail': 'ProjectFile not found'})

    with pytest.raises(httpx.HTTPStatusError):
        await api.upload(1, workspace.root / path, 'main.md', 7)


async def test_every_request_carries_lang(cloud, api):
    await api.me()
    request = cloud.router.calls.last.request
    assert request.url.params.get('lang') == 'ru'

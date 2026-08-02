from pathlib import Path

import pytest
import respx

from mgost.api import ArtichaAPI
from mgost.api.exceptions import APIRequestError
from tests.harness import BASE_URL


@pytest.fixture
async def api():
    async with ArtichaAPI('token', base_url=BASE_URL) as client:
        yield client


async def test_error_status_leaves_local_file_untouched(
    respx_mock: respx.MockRouter, api, workspace, clock
):
    path = Path('main.md')
    workspace.materialise(path, size=20, modified=clock.second_ago)
    original = workspace.read(path)
    respx_mock.get(
        f'{BASE_URL}/mgost/project/1/files/main.md'
    ).respond(500, json={'detail': 'Internal server error'})

    with pytest.raises(APIRequestError):
        await api.download(1, workspace.root, path, overwrite_ok=True)

    assert workspace.read(path) == original


async def test_error_status_leaves_no_temp_file(
    respx_mock: respx.MockRouter, api, workspace, clock
):
    path = Path('main.md')
    workspace.materialise(path, size=20, modified=clock.second_ago)
    respx_mock.get(
        f'{BASE_URL}/mgost/project/1/files/main.md'
    ).respond(404, json={'detail': 'ProjectFile not found'})

    with pytest.raises(APIRequestError):
        await api.download(1, workspace.root, path, overwrite_ok=True)

    assert workspace.paths() == {path}


async def test_refuses_to_overwrite_when_not_allowed(
    cloud, api, workspace, clock
):
    path = Path('main.md')
    cloud.add(path, size=20, modified=clock.second_ago)
    workspace.materialise(path, size=99, modified=clock.now)
    original = workspace.read(path)

    await api.download(
        cloud.project_id, workspace.root, path, overwrite_ok=False
    )

    assert workspace.read(path) == original


async def test_successful_download_replaces_and_stamps_mtime(
    cloud, api, workspace, clock
):
    path = Path('main.md')
    cloud.add(path, size=20, modified=clock.second_ago)

    await api.download(
        cloud.project_id, workspace.root, path, overwrite_ok=True
    )

    assert workspace.read(path) == cloud.read(path)
    assert workspace.modified(path) == clock.second_ago
    assert workspace.paths() == {path}

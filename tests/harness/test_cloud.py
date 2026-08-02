from hashlib import sha256
from os import utime
from pathlib import Path

import pytest
import respx
from httpx import Request

from mgost.api import ArtichaAPI
from tests.harness import BASE_URL, Call, FakeCloud


@pytest.fixture
def cloud(respx_mock: respx.MockRouter):
    c = FakeCloud(respx_mock)
    yield c
    c.close()


@pytest.fixture
async def api():
    async with ArtichaAPI('token', base_url=BASE_URL) as client:
        yield client


async def test_me(cloud, api):
    info = await api.me()
    assert info.name == 'Test'
    assert cloud.endpoints == ['me']


async def test_projects_lists_the_project(cloud, api):
    projects = await api.projects()
    assert [p.id for p in projects] == [cloud.project_id]


async def test_project_returns_files_and_paths(cloud, api, clock):
    cloud.add(Path('main.md'), size=20, modified=clock.second_ago)
    project = await api.project(cloud.project_id)
    assert project.path_to_markdown == Path('main.md')
    assert [f.path for f in project.files] == ['main.md']


async def test_project_files_keyed_by_path(cloud, api, clock):
    cloud.add(Path('images/i.png'), size=7, modified=clock.second_ago)
    files = await api.project_files(cloud.project_id)
    assert set(files) == {Path('images/i.png')}
    assert files[Path('images/i.png')].size == 7


async def test_project_files_carry_real_digest(cloud, api, clock):
    path = Path('main.md')
    cloud.add(path, size=20, modified=clock.second_ago)

    files = await api.project_files(cloud.project_id)

    assert files[path].hash == sha256(cloud.read(path)).hexdigest()
    assert len(files[path].hash) == 64
    assert files[path].hash == files[path].hash.lower()


async def test_empty_files_share_a_digest(cloud, api, clock):
    cloud.add(Path('a.md'), size=0, modified=clock.second_ago)
    cloud.add(Path('b.md'), size=0, modified=clock.second_ago)

    files = await api.project_files(cloud.project_id)

    assert files[Path('a.md')].hash == files[Path('b.md')].hash


async def test_requirements(cloud, api):
    cloud.requirements.append(Path('images/i.png'))
    reqs = await api.project_requirements(cloud.project_id)
    assert list(reqs) == ['images/i.png']


async def test_create_project_returns_new_id(cloud, api):
    new_id = await api.create_project('Another')
    assert new_id != cloud.project_id
    assert 'project_create' in cloud.endpoints


def test_call_of_extracts_target():
    request = Request('PATCH', 'https://x/f?target=sub%2Fb.md')
    assert Call.of(request, Path('a.md')) == Call(
        'PATCH', Path('a.md'), Path('sub/b.md')
    )


def test_call_of_leaves_target_none_without_param():
    request = Request('PUT', 'https://x/f')
    assert Call.of(request, Path('a.md')) == Call('PUT', Path('a.md'))


async def test_post_creates_file(cloud, api, tmp_path):
    (tmp_path / 'new.md').write_bytes(b'x' * 12)
    await api.upload(
        cloud.project_id, tmp_path, Path('new.md'), overwrite=False
    )
    assert cloud.exists(Path('new.md'))
    assert cloud.stat(Path('new.md')).st_size == 12
    assert cloud.file_calls() == [Call('POST', Path('new.md'))]


async def test_put_overwrites_and_updates_mtime(cloud, api, clock, tmp_path):
    cloud.add(Path('main.md'), size=20, modified=clock.seconds2_ago)
    local = tmp_path / 'main.md'
    local.write_bytes(b'y' * 33)
    utime(local, (clock.now.timestamp(), clock.now.timestamp()))

    await api.upload(
        cloud.project_id, tmp_path, Path('main.md'), overwrite=True
    )

    assert cloud.stat(Path('main.md')).st_size == 33
    assert cloud.modified(Path('main.md')) == clock.now
    assert cloud.file_calls() == [Call('PUT', Path('main.md'))]


async def test_get_returns_stored_bytes(cloud, api, clock, tmp_path):
    cloud.add(Path('main.md'), size=64, modified=clock.second_ago)
    await api.download(cloud.project_id, tmp_path, Path('main.md'))
    assert (tmp_path / 'main.md').read_bytes() == cloud.read(Path('main.md'))
    assert cloud.file_calls() == [Call('GET', Path('main.md'))]


async def test_patch_moves_and_records_target(cloud, api, clock, tmp_path):
    cloud.add(Path('main.md'), size=20, modified=clock.second_ago)

    await api.move_on_cloud(
        cloud.project_id, tmp_path, Path('main.md'), Path('sub/main.md')
    )

    assert cloud.paths() == {Path('sub/main.md')}
    assert cloud.file_calls() == [
        Call('PATCH', Path('main.md'), Path('sub/main.md'))
    ]


async def test_post_on_existing_file_is_rejected(cloud, api, clock, tmp_path):
    cloud.add(Path('main.md'), size=20, modified=clock.second_ago)
    (tmp_path / 'main.md').write_bytes(b'z' * 20)
    with pytest.raises(AssertionError, match='POST on existing'):
        await api.upload(
            cloud.project_id, tmp_path, Path('main.md'), overwrite=False
        )


async def test_put_on_missing_file_is_rejected(cloud, api, tmp_path):
    (tmp_path / 'ghost.md').write_bytes(b'z')
    with pytest.raises(AssertionError, match='PUT on missing'):
        await api.upload(
            cloud.project_id, tmp_path, Path('ghost.md'), overwrite=True
        )

from pathlib import Path

import pytest

from mgost.api import ArtichaAPI
from mgost.api.actions import FileMovedAndEditedLocally, FileMovedLocally
from tests.harness import BASE_URL, Call


@pytest.fixture
async def api():
    async with ArtichaAPI('token', base_url=BASE_URL) as client:
        yield client


def test_absolute_path_is_rejected(workspace):
    with pytest.raises(AssertionError):
        FileMovedLocally(
            workspace.root, 1,
            workspace.root / 'main.md', Path('docs/main.md'),
        )


async def test_move_patches_only(cloud, api, workspace, clock):
    cloud.add(Path('main.md'), size=20, modified=clock.second_ago)
    workspace.copy_from_cloud(
        cloud, Path('main.md'), Path('docs/main.md'), clock.seconds2_ago,
    )

    await FileMovedLocally(
        workspace.root, cloud.project_id,
        Path('main.md'), Path('docs/main.md'),
    ).complete_api(api)

    assert cloud.file_calls() == [
        Call('PATCH', Path('main.md'), Path('docs/main.md'))
    ]
    assert cloud.paths() == {Path('docs/main.md')}


async def test_move_and_edit_local_newer_patches_then_puts(
    cloud, api, workspace, clock
):
    cloud.add(Path('main.md'), size=20, modified=clock.second_ago)
    workspace.materialise(Path('docs/main.md'), size=21, modified=clock.now)

    await FileMovedAndEditedLocally(
        workspace.root, cloud.project_id,
        Path('main.md'), Path('docs/main.md'), local_newer=True,
    ).complete_api(api)

    assert [c.method for c in cloud.calls] == ['PATCH', 'PUT']
    assert cloud.read(Path('docs/main.md')) == workspace.read(
        Path('docs/main.md')
    )


async def test_move_and_edit_cloud_newer_patches_then_gets(
    cloud, api, workspace, clock
):
    cloud.add(Path('main.md'), size=20, modified=clock.now)
    workspace.materialise(
        Path('docs/main.md'), size=21, modified=clock.seconds2_ago
    )

    await FileMovedAndEditedLocally(
        workspace.root, cloud.project_id,
        Path('main.md'), Path('docs/main.md'), local_newer=False,
    ).complete_api(api)

    assert [c.method for c in cloud.calls] == ['PATCH', 'GET']
    assert workspace.read(Path('docs/main.md')) == cloud.read(
        Path('docs/main.md')
    )

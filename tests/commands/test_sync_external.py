"""Rows 14-20: requirements outside the project, stored as fictional files.

Sync only ever uploads them. Row numbers are documented in tests/README.md.
"""
from os import utime
from pathlib import Path

import pytest

from tests.harness import FOREIGN, Call

MD = Path('main.md')
DOCX = Path('output.docx')


@pytest.fixture
def settled(cloud, workspace, clock):
    """Markdown and docx identical on both sides, so only the external
    requirement can produce file calls."""
    for path, size in ((MD, 20), (DOCX, 100)):
        cloud.add(path, size=size, modified=clock.second_ago)
        workspace.copy_from_cloud(cloud, path, path, clock.second_ago)


@pytest.fixture
def outside(tmp_path):
    """A real file outside the workspace, written as an absolute path."""
    path = tmp_path / 'outside' / 'a.png'
    path.parent.mkdir()
    return path


def _write(path: Path, data: bytes, modified) -> None:
    path.write_bytes(data)
    utime(path, (modified.timestamp(), modified.timestamp()))


async def test_row14_local_only_posts_as_written(
    cloud, sync_project, clock, settled, outside
):
    _write(outside, b'x' * 10, clock.second_ago)
    cloud.requirements.append(str(outside))

    await sync_project()

    assert cloud.file_calls() == [Call('POST', Path(str(outside)))]
    assert list(cloud.fictional.values()) == [str(outside)]


async def test_row15_local_newer_puts(
    cloud, sync_project, clock, settled, outside
):
    cloud.add_fictional(str(outside), 10, clock.seconds2_ago)
    cloud.requirements.append(str(outside))
    _write(outside, b'y' * 11, clock.now)

    await sync_project()

    assert cloud.file_calls() == [Call('PUT', Path(str(outside)))]


async def test_row16_cloud_newer_still_puts_and_warns(
    cloud, sync_project, clock, settled, outside, capsys
):
    cloud.add_fictional(str(outside), 10, clock.now)
    cloud.requirements.append(str(outside))
    _write(outside, b'y' * 11, clock.seconds2_ago)

    await sync_project()

    assert cloud.file_calls() == [Call('PUT', Path(str(outside)))]
    assert 'новее' in capsys.readouterr().out


async def test_row17_identical_bytes_make_no_calls(
    cloud, sync_project, clock, settled, outside
):
    file_id = cloud.add_fictional(str(outside), 10, clock.seconds2_ago)
    cloud.requirements.append(str(outside))
    _write(outside, cloud.read(Path('.fictional') / str(file_id)), clock.now)

    await sync_project()

    assert cloud.file_calls() == []


@pytest.mark.parametrize('foreign', [False, True], ids=['deleted', 'foreign'])
async def test_row18_cloud_only_is_never_downloaded(
    cloud, sync_project, clock, settled, outside, capsys, foreign
):
    written = FOREIGN if foreign else str(outside)
    cloud.add_fictional(written, 10, clock.second_ago)
    cloud.requirements.append(written)

    await sync_project()

    assert cloud.file_calls() == []
    assert not outside.exists()
    assert 'копия из облака' in capsys.readouterr().out


async def test_row19_absolute_path_inside_project(
    cloud, workspace, sync_project, clock, settled, answers, capsys
):
    """notes.md is byte-identical to the missing chapter.md, so pass 1
    would PATCH chapter.md onto it, were it a move candidate."""
    answers(True)
    chapter = Path('chapter.md')
    cloud.add(chapter, size=30, modified=clock.second_ago)
    cloud.requirements.append(chapter)
    notes = workspace.copy_from_cloud(
        cloud, chapter, Path('notes.md'), clock.second_ago
    )
    cloud.requirements.append(str(notes))

    await sync_project()

    assert cloud.file_calls() == [
        Call('GET', chapter), Call('POST', Path(str(notes))),
    ]
    out = capsys.readouterr().out
    assert 'внутрь папки проекта' in out
    assert 'notes.md' in out


async def test_row20_missing_everywhere_makes_no_calls(
    cloud, sync_project, settled, outside
):
    cloud.requirements.append(str(outside))

    await sync_project()

    assert cloud.file_calls() == []

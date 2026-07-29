"""Scenario table for sync_file's four match branches.

Row numbers are documented in tests/README.md. Row 9 is deliberately
absent — it is a deferred design decision, not an oversight.
"""
from datetime import timedelta
from pathlib import Path

import pytest

from tests.harness import Call

MD = Path('main.md')
DOCX = Path('output.docx')


# --- Row 1: local only -----------------------------------------------------

async def test_row1_local_only_uploads(cloud, workspace, sync_project, clock):
    workspace.materialise(MD, size=20, modified=clock.second_ago)
    workspace.materialise(DOCX, size=21, modified=clock.second_ago)

    await sync_project()

    # file_calls() sorts by (method, path): 'main.md' < 'output.docx'
    assert cloud.file_calls() == [Call('POST', MD), Call('POST', DOCX)]
    workspace.assert_converged(cloud)


# --- Row 2: cloud only, nothing similar locally ----------------------------

async def test_row2_cloud_only_downloads(cloud, workspace, sync_project, clock):
    cloud.add(MD, size=20, modified=clock.second_ago)
    cloud.add(DOCX, size=21, modified=clock.second_ago)

    await sync_project()

    assert cloud.file_calls() == [Call('GET', MD), Call('GET', DOCX)]
    workspace.assert_converged(cloud)


# --- Row 5: both present, no meaningful time difference --------------------

@pytest.mark.parametrize(
    'skew_seconds', [0, 0.5], ids=['identical', 'sub-second'],
)
async def test_row5_no_action_within_dead_band(
    cloud, workspace, sync_project, clock, skew_seconds
):
    cloud.add(MD, size=20, modified=clock.second_ago)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    local_mtime = clock.second_ago + timedelta(seconds=skew_seconds)
    workspace.materialise(MD, size=20, modified=local_mtime)
    workspace.materialise(DOCX, size=100, modified=local_mtime)

    await sync_project()

    assert cloud.file_calls() == []


# --- Row 6: local newer ----------------------------------------------------

async def test_row6_local_newer_uploads(cloud, workspace, sync_project, clock):
    cloud.add(MD, size=20, modified=clock.second_ago)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(MD, size=21, modified=clock.now)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)

    await sync_project()

    assert cloud.file_calls() == [Call('PUT', MD)]
    workspace.assert_converged(cloud)


# --- Row 7: cloud newer  (regression guard) --------------------------------

async def test_row7_cloud_newer_downloads(
    cloud, workspace, sync_project, clock
):
    """timedelta.seconds is never negative — a -1s delta reports 86399,
    which made this branch unreachable until commit 7fa24a0."""
    cloud.add(MD, size=21, modified=clock.now)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(MD, size=20, modified=clock.second_ago)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)

    await sync_project()

    assert cloud.file_calls() == [Call('GET', MD)]
    workspace.assert_converged(cloud)


# --- Row 8: whole-day difference -------------------------------------------

async def test_row8_day_old_local_uploads(
    cloud, workspace, sync_project, clock
):
    """timedelta.seconds drops the days component: at exactly one day it
    returns 0 and the file is wrongly treated as in sync.

    The delta must be a whole day. At one day PLUS a second, .seconds
    returns 1, which still clears the dead band, and the row passes
    against the broken implementation without asserting anything.
    """
    cloud.add(MD, size=20, modified=clock.ago(days=1))
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(MD, size=21, modified=clock.now)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)

    await sync_project()

    assert cloud.file_calls() == [Call('PUT', MD)]
    workspace.assert_converged(cloud)


# --- Rows 3a-4c: is this local file the same file? -------------------------
#
# The cloud holds main.md; main.md is absent locally; one decoy file sits
# elsewhere in the tree. A decoy counts as the same file only when name AND
# size both match — reading down `expected` states that rule as data.
#
# All five are EXPECTED TO FAIL, and all five die the same way: sync_file
# builds FileMovedLocally with the ABSOLUTE full_path (sync.py:131) while
# PathAction.__post_init__ asserts the path is relative, so the whole
# move-detected branch raises before any request is made. 3a is correct
# behaviour and crashes with the rest.
#
# Two further defects in _search_file sit behind that one, and will
# surface on 3b/4a/4b/4c once it is fixed. See tests/README.md.
#
# Do not fix src/. Do not xfail these.

@pytest.mark.parametrize(
    'decoy_path, decoy_size, cloud_size, expected',
    [
        (Path('docs/main.md'), 20, 20, 'PATCH'),
        (Path('docs/main.md'), 21, 20, 'GET'),
        (Path('unrelated.txt'), 0, 0, 'GET'),
        (Path('unrelated.txt'), 64, 64, 'GET'),
        (Path('unrelated.txt'), 358_400, 358_400, 'GET'),
    ],
    ids=['3a', '3b', '4a', '4b', '4c'],
)
async def test_rows3_4_move_detection(
    cloud, workspace, sync_project, clock,
    decoy_path, decoy_size, cloud_size, expected,
):
    cloud.add(MD, size=cloud_size, modified=clock.second_ago)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)
    # The decoy's mtime is never the cloud file's `created`, so the
    # st_birthtime branch stays dead on every platform.
    workspace.materialise(
        decoy_path, size=decoy_size, modified=clock.seconds2_ago
    )

    await sync_project()

    md_calls = [c for c in cloud.file_calls() if c.path == MD]
    assert [c.method for c in md_calls] == [expected]


# --- Requirements ----------------------------------------------------------

@pytest.mark.parametrize(
    'requirement',
    [Path('image.png'), Path('images/image.png')],
    ids=['flat', 'nested'],
)
async def test_local_requirement_is_uploaded(
    cloud, workspace, sync_project, clock, requirement
):
    cloud.add(MD, size=25, modified=clock.second_ago)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    cloud.requirements.append(requirement)
    workspace.materialise(MD, size=21, modified=clock.now)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(requirement, size=100, modified=clock.now)

    await sync_project()

    # 'POST' < 'PUT', so the requirement upload sorts first
    assert cloud.file_calls() == [
        Call('POST', requirement), Call('PUT', MD),
    ]
    workspace.assert_converged(cloud)


# --- Row 10: requirement present nowhere -----------------------------------

async def test_row10_missing_requirement_makes_no_file_calls(
    cloud, workspace, sync_project, clock
):
    """The server warns about this during render anyway — see
    tests/README.md on avoiding a duplicated message."""
    ghost = Path('ghost.png')
    cloud.add(MD, size=20, modified=clock.second_ago)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    cloud.requirements.append(ghost)
    workspace.materialise(MD, size=20, modified=clock.second_ago)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)

    await sync_project()

    assert [c for c in cloud.file_calls() if c.path == ghost] == []

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


# --- Rows 3a-4c, 11-13: is this local file the same file? ------------------
#
# The cloud holds main.md; main.md is absent locally; decoys sit
# elsewhere in the tree. Reading down `expected` states the rule as data.

async def test_row3a_exact_digest_patches(
    cloud, workspace, sync_project, clock, answers
):
    answers(True)
    cloud.add(MD, size=20, modified=clock.second_ago)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)
    workspace.copy_from_cloud(
        cloud, MD, Path('docs/main.md'), modified=clock.seconds2_ago
    )

    await sync_project()

    assert [c for c in cloud.file_calls() if c.path == MD] == [
        Call('PATCH', MD, Path('docs/main.md'))
    ]


@pytest.mark.parametrize(
    'decoy_mtime_attr, second_call',
    [('seconds2_ago', 'GET'), ('now', 'PUT')],
    ids=['3b-cloud-newer', '3c-local-newer'],
)
async def test_rows3b_3c_moved_and_edited(
    cloud, workspace, sync_project, clock, answers,
    decoy_mtime_attr, second_call,
):
    answers(True)
    cloud.add(MD, size=20, modified=clock.second_ago)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(
        Path('docs/main.md'), size=21,
        modified=getattr(clock, decoy_mtime_attr),
    )

    await sync_project()

    assert [c.method for c in cloud.calls] == ['PATCH', second_call]


@pytest.mark.parametrize(
    'size', [0, 64, 358_400], ids=['4a', '4b', '4c'],
)
async def test_rows4_unrelated_file_downloads(
    cloud, workspace, sync_project, clock, answers, size
):
    """4a's bytes ARE equal - every empty file hashes alike. The size > 0
    guard rejects it, not the digest."""
    answers(True, interactive=False)
    cloud.add(MD, size=size, modified=clock.second_ago)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(
        Path('unrelated.txt'), size=size, modified=clock.seconds2_ago
    )

    await sync_project()

    assert [c for c in cloud.file_calls() if c.path == MD] == [
        Call('GET', MD)
    ]


async def test_row11_tracked_file_is_not_a_candidate(
    cloud, workspace, sync_project, clock, answers
):
    """notes.md is byte-identical to main.md and present locally.
    Without the tracked-path exclusion, pass 1 claims it and PATCHes
    main.md over a real file."""
    answers(True)
    cloud.add(MD, size=20, modified=clock.second_ago)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)
    cloud.write(Path('notes.md'), cloud.read(MD), clock.second_ago)
    workspace.copy_from_cloud(
        cloud, MD, Path('notes.md'), modified=clock.second_ago
    )

    await sync_project()

    assert [c for c in cloud.file_calls() if c.path == MD] == [
        Call('GET', MD)
    ]


async def test_row12_two_candidates_sharing_a_name_download(
    cloud, workspace, sync_project, clock, answers
):
    """The several-markdown-files case."""
    answers(True)
    cloud.add(MD, size=20, modified=clock.second_ago)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(Path('docs/main.md'), 21, clock.now)
    workspace.materialise(Path('archive/main.md'), 22, clock.now)

    await sync_project()

    assert [c for c in cloud.file_calls() if c.path == MD] == [
        Call('GET', MD)
    ]


@pytest.mark.parametrize(
    'answer, interactive, expected',
    [(True, True, ['PATCH', 'PUT']), (True, False, ['GET'])],
    ids=['13-confirmed', '13-unattended'],
)
async def test_row13_sole_remainder(
    cloud, workspace, sync_project, clock, answers,
    answer, interactive, expected,
):
    answers(answer, interactive=interactive)
    cloud.add(MD, size=20, modified=clock.second_ago)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(Path('chapter.md'), size=21, modified=clock.now)

    await sync_project()

    assert [c.method for c in cloud.calls] == expected


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

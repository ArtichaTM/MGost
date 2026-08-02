from datetime import timedelta
from pathlib import Path

MD = Path('main.md')
DOCX = Path('output.docx')


async def test_identical_bytes_skip_transfer_despite_skew(
    cloud, workspace, sync_project, clock
):
    """Clock skew between machine and server must not move bytes that
    are already the same on both sides."""
    cloud.add(MD, size=20, modified=clock.ago(days=1))
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.copy_from_cloud(cloud, MD, MD, modified=clock.now)
    workspace.copy_from_cloud(cloud, DOCX, DOCX, clock.second_ago)

    await sync_project()

    assert cloud.file_calls() == []


async def test_differing_bytes_still_transfer(
    cloud, workspace, sync_project, clock
):
    """`filler()` is path-seeded, so materialising MD on both sides at
    the same size would coincidentally produce identical bytes. Writing
    explicit content keeps this a genuine divergence."""
    cloud.add(MD, size=20, modified=clock.second_ago)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.write(MD, b'y' * 20, clock.now + timedelta(0))
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)

    await sync_project()

    assert [c.method for c in cloud.file_calls()] == ['PUT']

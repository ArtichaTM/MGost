from pathlib import Path

from tests.harness import Call

MD = Path('main.md')
DOCX = Path('output.docx')


async def test_pass2_accepts_by_default(
    cloud, workspace, sync_project, clock, answers
):
    answers(True)
    cloud.add(MD, size=20, modified=clock.second_ago)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(Path('docs/main.md'), size=21, modified=clock.now)

    await sync_project()

    assert [c.method for c in cloud.calls] == ['PATCH', 'PUT']


async def test_pass2_declined_downloads(
    cloud, workspace, sync_project, clock, answers
):
    answers(False)
    cloud.add(MD, size=20, modified=clock.second_ago)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(Path('docs/main.md'), size=21, modified=clock.now)

    await sync_project()

    assert [c for c in cloud.file_calls() if c.path == MD] == [
        Call('GET', MD)
    ]


async def test_pass3_declines_when_unattended(
    cloud, workspace, sync_project, clock, answers
):
    """Pass 3 has no content evidence. Console.confirm returns True when
    unattended, so pass 3 must test is_prompts itself."""
    answers(True, interactive=False)
    cloud.add(MD, size=20, modified=clock.second_ago)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(Path('chapter.md'), size=21, modified=clock.now)

    await sync_project()

    assert [c for c in cloud.file_calls() if c.path == MD] == [
        Call('GET', MD)
    ]


async def test_missing_markdown_reports(
    cloud, workspace, sync_project, clock, answers, capsys
):
    """A PostProgressMessageAction produced for the markdown is dropped
    today, because only the requirement subset is scanned."""
    answers(True)
    cloud.add(DOCX, size=100, modified=clock.second_ago)
    workspace.materialise(DOCX, size=100, modified=clock.second_ago)

    await sync_project()

    assert 'main.md' in capsys.readouterr().out

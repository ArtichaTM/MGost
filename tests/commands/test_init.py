import sys
from io import StringIO
from pathlib import Path

import pytest

from mgost.cli import async_commands
from mgost.mgost import MGost


def _raise_keyboard_interrupt(*args, **kwargs):
    """Simulate Ctrl+C at the prompt."""
    raise KeyboardInterrupt()


async def test_init_creates_project_and_markdown(
    cloud, workspace, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(sys, 'stdin', StringIO('0\nTestPut'))

    mgost = MGost(workspace.root)
    async with mgost:
        await mgost.init()

    assert workspace.exists(Path('main.md'))
    assert cloud.endpoints == ['projects', 'project_create', 'examples']
    assert cloud.file_calls() == []


async def test_init_interrupted_leaves_no_files(
    cloud, workspace, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr('typer.prompt', _raise_keyboard_interrupt)

    with pytest.raises(KeyboardInterrupt):
        await async_commands.init(workspace.root)

    assert workspace.paths() == set()
    # async_commands.init validates the token first; MGost.init alone does
    # not. The old harness never yielded the /me route, so this went
    # unchecked for the whole life of the suite.
    assert cloud.endpoints == ['me', 'projects']

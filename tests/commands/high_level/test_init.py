import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pytest
import respx

from mgost.api.schemas.mgost import ProjectExtended
from mgost.cli import async_commands
from mgost.mgost import MGost

from ..environment.helper import EnvironmentHelper, ExitChecks
from .utils import raise_keyboard_interrupt


@pytest.mark.asyncio
async def test_init(
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: respx.MockRouter
):
    project_id = 1
    now = datetime.now(timezone.utc)
    env = EnvironmentHelper(
        respx_mock=respx_mock,
        project=ProjectExtended(
            name='Test',
            id=project_id,
            created=now,
            modified=now,
            path_to_markdown=Path('main.md'),
            path_to_docx=Path('output.docx'),
            files=[]
        ),
        local_files=[],
        new_local_files=[
            {
                'path': 'main.md'
            }
        ],
        exit_checks=ExitChecks.NEW_LOCAL_FILES_CREATED
    )
    async with env:
        assert env.temp_dir_local is not None
        root_path = Path(env.temp_dir_local.name)
        mgost = MGost(root_path)
        monkeypatch.setenv("ARTICHAAPI_TOKEN", '1')
        monkeypatch.setattr(sys, 'stdin', StringIO('0\nTestPut'))
        async with mgost:
            await mgost.init()
        env.routes.assert_all_not_called_except(
            env.routes.projects,
            env.routes.project_put,
            env.routes.examples
        )


@pytest.mark.asyncio
async def test_init_kb_interrupt_launch(
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: respx.MockRouter
):
    monkeypatch.setenv("ARTICHAAPI_TOKEN", '1')
    monkeypatch.setattr('typer.prompt', raise_keyboard_interrupt)
    now = datetime.now(timezone.utc)
    env = EnvironmentHelper(
        respx_mock=respx_mock,
        project=ProjectExtended(
            name='Test',
            id=1,
            created=now,
            modified=now,
            path_to_markdown=Path('main.md'),
            path_to_docx=Path('output.docx'),
            files=[]
        ),
        local_files=[]
    )
    async with env:
        assert env.temp_dir_local is not None
        root_path = Path(env.temp_dir_local.name)
        with pytest.raises(KeyboardInterrupt):
            await async_commands.init(root_path)
        env.routes.assert_all_not_called_except(
            env.routes.projects
        )
        exceptions: list[FileExistsError] = []
        for file in root_path.iterdir():
            exceptions.append(FileExistsError(
                f"{file.relative_to(root_path)} is created"
            ))
        if exceptions:
            raise ExceptionGroup(
                "There's a files created when library is "
                "not used",
                exceptions
            )

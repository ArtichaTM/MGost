import sys
from datetime import datetime
from io import StringIO
from pathlib import Path

import pytest
import respx

from mgost.api.schemas.mgost import ProjectExtended
from mgost.mgost import MGost

from ..environment.helper import EnvironmentHelper, ExitChecks


@pytest.mark.asyncio
async def test_init(
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: respx.MockRouter
):
    project_id = 1
    now = datetime.now().astimezone()
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

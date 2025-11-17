from datetime import datetime, timedelta
from pathlib import Path

import pytest
import respx

from mgost.api.schemas.mgost import ProjectExtended, ProjectFile
from mgost.mgost import MGost

from ..environment.helper import EnvironmentHelper


@pytest.mark.asyncio
async def test_upload(
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: respx.MockRouter
):
    project_id = 1
    now = datetime.now().astimezone()
    second_ago = now - timedelta(seconds=1)
    seconds2_ago = now - timedelta(seconds=2)
    env = EnvironmentHelper(
        respx_mock=respx_mock,
        project=ProjectExtended(
            name='Test',
            id=project_id,
            created=second_ago,
            modified=now,
            path_to_markdown=Path('main.md'),
            path_to_docx=Path('output.docx'),
            files=[
                ProjectFile(
                    project_id=project_id,
                    path='main.md',
                    created=seconds2_ago,
                    modified=second_ago,
                    size=20
                ),
            ]
        ),
        local_files=[
            ProjectFile(
                project_id=project_id,
                path='main.md',
                created=seconds2_ago,
                modified=now,
                size=21
            ),
        ]
    )
    async with env:
        assert env.temp_dir_local is not None
        root_path = Path(env.temp_dir_local.name)
        mgost = MGost(root_path)
        monkeypatch.setenv("ARTICHAAPI_TOKEN", '1')
        async with mgost:
            mgost.info.settings.project_id = 1
            mgost.info.settings.project_name = 'Test'
            await mgost.sync_files()
        env.routes.assert_all_not_called_except(
            env.routes.project,
            env.routes.project_requirements,
            env.routes.project_files,
            env.routes.file.existing.post[Path('main.md')]
        )


@pytest.mark.asyncio
async def test_download(
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: respx.MockRouter
):
    project_id = 1
    now = datetime.now().astimezone()
    second_ago = now - timedelta(seconds=1)
    seconds2_ago = now - timedelta(seconds=2)
    env = EnvironmentHelper(
        respx_mock=respx_mock,
        project=ProjectExtended(
            name='Test',
            id=project_id,
            created=second_ago,
            modified=now,
            path_to_markdown=Path('main.md'),
            path_to_docx=Path('output.docx'),
            files=[
                ProjectFile(
                    project_id=project_id,
                    path='main.md',
                    created=seconds2_ago,
                    modified=now,
                    size=21
                ),
            ]
        ),
        local_files=[
            ProjectFile(
                project_id=project_id,
                path='main.md',
                created=seconds2_ago,
                modified=second_ago,
                size=20
            ),
        ]
    )
    async with env:
        assert env.temp_dir_local is not None
        root_path = Path(env.temp_dir_local.name)
        mgost = MGost(root_path)
        monkeypatch.setenv("ARTICHAAPI_TOKEN", '1')
        async with mgost:
            mgost.info.settings.project_id = 1
            mgost.info.settings.project_name = 'Test'
            await mgost.sync_files()
        assert env.routes.project.called
        assert env.routes.project_requirements.called
        assert env.routes.project_files.called
        assert env.routes.file.existing.get[Path('main.md')].called

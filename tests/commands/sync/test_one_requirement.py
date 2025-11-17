from datetime import datetime, timedelta
from pathlib import Path

import pytest
import respx

from mgost.api.schemas.mgost import (
    FileRequirement, ProjectExtended, ProjectFile
)
from mgost.mgost import MGost

from ..environment.helper import EnvironmentHelper


@pytest.mark.asyncio
async def test_one_png(
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
                    size=25
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
            ProjectFile(
                project_id=project_id,
                path='image.png',
                created=second_ago,
                modified=now,
                size=100
            ),
        ],
        requirements=[
            FileRequirement(
                path='image.png'
            )
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
            env.routes.file.existing.post[Path('main.md')],
            env.routes.file.new.put[Path('image.png')]
        )


@pytest.mark.asyncio
async def test_one_png_with_directory(
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: respx.MockRouter
):
    project_id = 1
    now = datetime.now().astimezone()
    second_ago = now - timedelta(seconds=1)
    seconds2_ago = now - timedelta(seconds=2)
    req_path = str(Path('images/image.png'))
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
                    size=25
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
            ProjectFile(
                project_id=project_id,
                path=req_path,
                created=second_ago,
                modified=now,
                size=100
            ),
        ],
        requirements=[
            FileRequirement(
                path=req_path
            )
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
            env.routes.file.existing.post[Path('main.md')],
            env.routes.file.new.put[Path(req_path)]
        )

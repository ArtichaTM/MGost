from datetime import datetime, timedelta
from pathlib import Path

import pytest
import respx

from mgost.api.schemas.mgost import ProjectExtended, ProjectFile

from ..environment.helper import EnvironmentHelper


@pytest.mark.asyncio
async def test_only_md(respx_mock: respx.MockRouter):
    project_id = 1
    now = datetime.now()
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
                modified=second_ago,
                size=20
            ),
        ]
    )
    async with env:
        pass


@pytest.mark.asyncio
async def test_md_docx(respx_mock: respx.MockRouter):
    project_id = 1
    now = datetime.now()
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
                ProjectFile(
                    project_id=project_id,
                    path='output.docx',
                    created=seconds2_ago,
                    modified=second_ago,
                    size=200
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
            ProjectFile(
                project_id=project_id,
                path='output.docx',
                created=seconds2_ago,
                modified=second_ago,
                size=200
            ),
        ]
    )
    async with env:
        pass

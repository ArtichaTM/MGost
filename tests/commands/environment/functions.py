from datetime import datetime, timedelta
from pathlib import Path

import respx

from mgost.api.schemas.mgost import ProjectExtended, ProjectFile
from tests.commands.environment.helper import EnvironmentHelper


def create_simple_environment(
    respx_mock: respx.MockRouter
) -> EnvironmentHelper:
    project_id = 1
    now = datetime.now()
    second_ago = now - timedelta(seconds=1)
    project_files = [
        ProjectFile(
            project_id=project_id,
            path='main.md',
            created=second_ago,
            modified=now,
            size=20
        ),
        ProjectFile(
            project_id=project_id,
            path='output.docx',
            created=second_ago,
            modified=now,
            size=200
        ),
    ]
    return EnvironmentHelper(
        respx_mock=respx_mock,
        project=ProjectExtended(
            name='Test',
            id=project_id,
            created=second_ago,
            modified=now,
            path_to_markdown=Path('main.md'),
            path_to_docx=Path('output.docx'),
            files=project_files
        ),
        local_files=project_files,
        requirements=dict()
    )

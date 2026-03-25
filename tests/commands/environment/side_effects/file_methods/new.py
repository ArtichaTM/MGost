from datetime import datetime
from pathlib import Path

from httpx import Request, Response

from mgost.api.schemas.mgost import ProjectFile

from .base import FileMethodsBase


class NewFileMethods(FileMethodsBase):
    async def put(self, request: Request) -> Response:
        raise AssertionError(self._message(
            "PUT non-existing", request
        ))

    async def post(self, request: Request) -> Response:
        path = self.env._file_path_from_url(request.url.path)
        file = self.env._file_from_path(request.url.path)
        assert file is None
        modify_time = request.url.params.get('modify_time', None)
        assert modify_time is not None
        assert isinstance(modify_time, str)
        modify_time = datetime.fromisoformat(modify_time)
        file = ProjectFile(
            project_id=self.env.project.id,
            path=str(Path(path)),
            created=modify_time,
            modified=modify_time,
            size=len(request.read())
        )
        file.modified = modify_time
        size = len(request.read())
        file.size = size
        self.env.project.files.append(file)
        return Response(
            status_code=201,
            json=file.model_dump(mode='json')
        )

    async def patch(self, request: Request) -> Response:
        raise AssertionError(self._message(
            "PATCH non-existing", request
        ))

    async def delete(self, request: Request) -> Response:
        raise AssertionError(self._message(
            "DELETE non-existing", request
        ))

    async def get(self, request: Request) -> Response:
        raise AssertionError(self._message(
            "GET non-existing", request
        ))

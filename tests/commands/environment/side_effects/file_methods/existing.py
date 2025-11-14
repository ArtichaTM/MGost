from datetime import datetime
from random import randbytes

from httpx import Request, Response

from mgost.api.schemas.mgost import Message

from .base import FileMethodsBase


class ExistingFileMethods(FileMethodsBase):
    async def put(self, request: Request) -> Response:
        raise AssertionError("App tries to PUT existing file")

    async def post(self, request: Request) -> Response:
        path = self.env._file_path_from_url(request.url.path)
        file = self.env._file_from_path(path)
        assert file
        modify_time = request.url.params.get('modify_time', None)
        assert modify_time is not None
        assert isinstance(modify_time, str)
        modify_time = datetime.fromisoformat(modify_time)
        file.modified = modify_time
        size = len(request.read())
        file.size = size
        return Response(
            status_code=200,
            json=Message().model_dump(mode='json')
        )

    async def patch(self, request: Request) -> Response:
        path = self.env._file_path_from_url(request.url.path)
        file = self.env._file_from_path(path)
        assert file
        assert 'target' in request.url.params
        target = request.url.params['target']
        file.path = target
        return Response(
            status_code=200,
            json=Message().model_dump(mode='json')
        )

    async def delete(self, request: Request) -> Response:
        path = self.env._file_path_from_url(request.url.path)
        assert path
        found = False
        _i = None
        for _i, file in enumerate(self.env.project.files):
            if file.path == path:
                found = True
                break
        assert _i is not None
        assert found
        self.env.project.files.pop(_i)
        return Response(
            status_code=200,
            json=Message().model_dump(mode='json')
        )

    async def get(self, request: Request) -> Response:
        path = self.env._file_path_from_url(request.url.path)
        file = self.env._file_from_path(path)
        assert file
        return Response(status_code=200, content=randbytes(file.size))

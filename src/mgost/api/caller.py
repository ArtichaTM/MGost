from asyncio import sleep
from functools import partial
from json import JSONDecodeError
from typing import Awaitable

from aiopath import AsyncPath
from httpx import AsyncClient, QueryParams, Response

from .exceptions import APIRequestError
from .request import APIRequestInfo


def api_request(
    client: AsyncClient,
    cache: dict,
    request: APIRequestInfo,
) -> Awaitable[Response]:
    assert isinstance(client, AsyncClient)
    assert request.url.startswith('/')
    assert isinstance(request.url, str)
    params = request.params
    if params is None:
        params = QueryParams()
    assert isinstance(params, (dict, QueryParams))
    if request.with_progress():
        return _method_progress(
            client=client,
            request=request,
        )
    return _method_normal(
        client=client,
        cache=cache,
        request=request,
    )


async def _method_normal(
    client: AsyncClient,
    cache: dict,
    request: APIRequestInfo
) -> Response:
    key = (request.method, request.url, request.params, request.files)
    try:
        if (value := cache.get(key)) is not None:
            return value
    except TypeError:
        key = None
    func = partial(
        client.request,
        method=request.method,
        url=request.url,
        params=request.params,
        files=request.files
    )
    resp = await func()
    counter = 0
    while resp.status_code == 429:
        await sleep(5)
        resp = await func()
        counter += 1
        if counter > 2:
            break
    resp.raise_for_status()
    try:
        info = resp.json()
        if 'detail' in info:
            raise APIRequestError(
                resp, info['detail']
            )
    except (JSONDecodeError, UnicodeDecodeError):
        pass
    if key is not None:
        cache[key] = resp
    return resp


def _method_progress(
    client: AsyncClient,
    request: APIRequestInfo
) -> Awaitable[Response]:
    if request.files:
        return _method_progress_upload(client, request)
    return _method_progress_download(client, request)


async def _file_chunker(file_path: AsyncPath, chunk_size=65536):
    with open(file_path, 'rb') as file:
        while chunk := file.read(chunk_size):
            yield chunk


async def _method_progress_upload(
    client: AsyncClient,
    request: APIRequestInfo
) -> Response:
    assert request.request_file_path is not None
    assert request.progress is not None
    request.progress.add_task(
        description=f"↑ {request.request_file_path}"
    )
    request.request_file_path.lstat().st_size
    response = await client.request(
        request.method, request.url,
        content=_file_chunker(
            request.request_file_path
        )
    )
    return response


async def _method_progress_download(
    client: AsyncClient,
    request: APIRequestInfo
) -> Response:
    assert request.response_file_path is not None
    assert request.progress is not None
    task = request.progress.add_task(
        description=f"↓ {request.response_file_path}"
    )
    total = None
    async with client.stream(
        request.method, request.url,
        params=request.params
    ) as resp:
        if 'content-length' in resp.headers:
            total = int(resp.headers['content-length'])
        request.progress.update(
            task,
            total=total,
            visible=True
        )
        async with request.response_file_path.open('wb') as file:
            async for chunk in resp.aiter_bytes():
                request.progress.update(task, advance=len(chunk))
                await file.write(chunk)
        return resp

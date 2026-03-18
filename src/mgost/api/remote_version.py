import httpx


def get_remote_version(timeout: float = 1.) -> str | None:
    try:
        response = httpx.get(
            "https://pypi.org/pypi/mgost/json",
            timeout=timeout
        )
    except TimeoutError:
        return
    data = response.json()
    assert data.get('message') != 'Not Found'
    return data['info']['version']

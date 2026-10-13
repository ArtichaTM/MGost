import io
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import respx
from typer.testing import CliRunner

from mgost.api import ArtichaAPI
from mgost.api.schemas import TokenInfo
from mgost.cli import app
from mgost.console import Console
from mgost.mgost import fast_convert as module
from mgost.mgost.fast_convert import fast_convert
from tests.harness import BASE_URL

MARKDOWN = '# Заголовок\n'.encode()
DOCX = b'PK\x03\x04docx'
CONVERT_URL = f'{BASE_URL}/mgost/fast-convert'
OUTPUT_URL = f'{BASE_URL}/mgost/fast-convert/output'


def conversion(finished: bool = True, running: bool = False) -> dict:
    return {
        'max_log_level': 20,
        'logs': [{'level': 30, 'message': 'warning'}],
        'finished': finished,
        'running': running,
        'output_url': '/mgost/fast-convert/output',
    }


@pytest.fixture(autouse=True)
def _cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, 'POLL_INTERVAL', 0)
    return tmp_path


@pytest.fixture
def me(respx_mock: respx.MockRouter) -> respx.Route:
    now = datetime.now(UTC)
    info = TokenInfo(name='t', owner='o', created=now, modified=now)
    return respx_mock.get(f'{BASE_URL}/me').respond(
        200, json=info.model_dump(mode='json')
    )


@pytest.fixture
def stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, 'stdin', io.TextIOWrapper(io.BytesIO(MARKDOWN)))


@pytest.fixture
def prompted_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('ARTICHAAPI_TOKEN')
    monkeypatch.setattr(
        type(Console), 'prompt', lambda self, *a, **kw: 'typed'
    )


async def test_default_source(
    respx_mock: respx.MockRouter, me, _cwd: Path
):
    (_cwd / 'main.md').write_bytes(MARKDOWN)
    post = respx_mock.post(CONVERT_URL).respond(200, json=conversion())
    respx_mock.get(OUTPUT_URL).respond(200, content=DOCX)

    assert await fast_convert(None, None)

    assert (_cwd / 'main.docx').read_bytes() == DOCX
    request = post.calls.last.request
    assert request.content == MARKDOWN
    assert request.headers['Content-Type'] == 'application/octet-stream'
    assert not (_cwd / '.mgost').exists()


async def test_missing_default_source(respx_mock: respx.MockRouter):
    assert not await fast_convert(None, None)
    assert not respx_mock.calls


async def test_explicit_output(
    respx_mock: respx.MockRouter, me, _cwd: Path
):
    (_cwd / 'notes.md').write_bytes(MARKDOWN)
    respx_mock.post(CONVERT_URL).respond(200, json=conversion())
    respx_mock.get(OUTPUT_URL).respond(200, content=DOCX)

    assert await fast_convert(Path('notes.md'), Path('out/report.docx'))

    assert (_cwd / 'out' / 'report.docx').read_bytes() == DOCX
    assert not (_cwd / 'notes.docx').exists()


async def test_output_overwritten(
    respx_mock: respx.MockRouter, me, _cwd: Path
):
    (_cwd / 'main.md').write_bytes(MARKDOWN)
    (_cwd / 'main.docx').write_bytes(b'old')
    respx_mock.post(CONVERT_URL).respond(200, json=conversion())
    respx_mock.get(OUTPUT_URL).respond(200, content=DOCX)

    assert await fast_convert(None, None)
    assert (_cwd / 'main.docx').read_bytes() == DOCX


async def test_running_polls_until_ready(
    respx_mock: respx.MockRouter, me, _cwd: Path
):
    (_cwd / 'main.md').write_bytes(MARKDOWN)
    respx_mock.post(CONVERT_URL).respond(
        200, json=conversion(finished=False, running=True)
    )
    output = respx_mock.get(OUTPUT_URL)
    output.side_effect = [
        respx.MockResponse(409), respx.MockResponse(409),
        respx.MockResponse(200, content=DOCX),
    ]

    assert await fast_convert(None, None)
    assert output.call_count == 3
    assert (_cwd / 'main.docx').read_bytes() == DOCX


async def test_running_times_out(
    respx_mock: respx.MockRouter, me, _cwd: Path,
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(ArtichaAPI, 'RENDER_TIMEOUT', 0.)
    (_cwd / 'main.md').write_bytes(MARKDOWN)
    respx_mock.post(CONVERT_URL).respond(
        200, json=conversion(finished=False, running=True)
    )
    respx_mock.get(OUTPUT_URL).respond(409)

    assert not await fast_convert(None, None)
    assert not (_cwd / 'main.docx').exists()


async def test_failed_render_skips_download(
    respx_mock: respx.MockRouter, me, _cwd: Path
):
    (_cwd / 'main.md').write_bytes(MARKDOWN)
    respx_mock.post(CONVERT_URL).respond(
        200, json=conversion(finished=False)
    )
    output = respx_mock.get(OUTPUT_URL).respond(200, content=DOCX)

    assert not await fast_convert(None, None)
    assert output.call_count == 0


async def test_busy_retried_once(
    respx_mock: respx.MockRouter, me, _cwd: Path
):
    (_cwd / 'main.md').write_bytes(MARKDOWN)
    post = respx_mock.post(CONVERT_URL)
    post.side_effect = [
        respx.MockResponse(409, json={'detail': 'busy'}),
        respx.MockResponse(200, json=conversion()),
    ]
    respx_mock.get(OUTPUT_URL).respond(200, content=DOCX)

    assert await fast_convert(None, None)
    assert post.call_count == 2


async def test_busy_twice_gives_up(
    respx_mock: respx.MockRouter, me, _cwd: Path
):
    (_cwd / 'main.md').write_bytes(MARKDOWN)
    post = respx_mock.post(CONVERT_URL).respond(409, json={'detail': 'busy'})

    assert not await fast_convert(None, None)
    assert post.call_count == 2


async def test_stdin_to_stdout(
    respx_mock: respx.MockRouter, me, stdin,
    capsysbinary: pytest.CaptureFixture[bytes]
):
    post = respx_mock.post(CONVERT_URL).respond(200, json=conversion())
    respx_mock.get(OUTPUT_URL).respond(200, content=DOCX)

    assert await fast_convert(Path('-'), Path('-'))

    captured = capsysbinary.readouterr()
    assert captured.out == DOCX
    assert 'Документ записан в stdout' in captured.err.decode()
    assert post.calls.last.request.content == MARKDOWN
    assert Console.err is False


async def test_stdin_requires_output(respx_mock: respx.MockRouter, stdin):
    assert not await fast_convert(Path('-'), None)
    assert not respx_mock.calls


async def test_stdin_without_stored_token(
    respx_mock: respx.MockRouter, stdin, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv('ARTICHAAPI_TOKEN')
    assert not await fast_convert(Path('-'), Path('out.docx'))
    assert not respx_mock.calls


@pytest.mark.parametrize('save', [True, False], ids=['saved', 'not-saved'])
async def test_prompted_token(
    respx_mock: respx.MockRouter, me, _cwd: Path,
    prompted_token, answers, save: bool
):
    answers(save)
    (_cwd / 'main.md').write_bytes(MARKDOWN)
    respx_mock.post(CONVERT_URL).respond(200, json=conversion())
    respx_mock.get(OUTPUT_URL).respond(200, content=DOCX)

    assert await fast_convert(None, None)

    assert me.calls.last.request.headers['X-API-Key'] == 'typed'
    dotenv = _cwd / '.mgost' / '.env'
    assert dotenv.exists() is save
    if save:
        assert dotenv.read_text() == 'ARTICHAAPI_TOKEN=typed'


def test_cli_exit_code(respx_mock: respx.MockRouter):
    result = CliRunner().invoke(app, ['convert'])
    assert result.exit_code == 1
    assert 'SOURCE не указан' in result.output

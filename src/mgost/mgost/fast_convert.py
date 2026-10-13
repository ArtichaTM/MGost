"""Project-less conversion of a single markdown file"""
import sys
from asyncio import sleep
from os import replace
from pathlib import Path
from time import monotonic

from httpx import HTTPStatusError, TimeoutException

from mgost.api import ArtichaAPI
from mgost.api.schemas.mgost import FastConversionResult
from mgost.console import Console
from mgost.settings import API_KEY_SOURCE, ApiKeyHolder

from .utils import print_build_result, token_valid

__all__ = ('DEFAULT_SOURCE', 'STDIO', 'fast_convert')

STDIO = Path('-')
DEFAULT_SOURCE = Path('main.md')
# Seconds between attempts while the server is busy
POLL_INTERVAL = 2.


async def fast_convert(source: Path | None, output: Path | None) -> bool:
    """Converts `source` into `output`, `-` meaning stdin/stdout.
    Returns whether the document was written
    """
    Console.err = output == STDIO
    try:
        return await _fast_convert(source, output)
    finally:
        Console.nl().finalize()
        Console.err = False


async def _fast_convert(source: Path | None, output: Path | None) -> bool:
    if source is None:
        if not DEFAULT_SOURCE.is_file():
            _error('SOURCE не указан', f', а {DEFAULT_SOURCE} не найден')
            return False
        source = DEFAULT_SOURCE
    if output is None:
        if source == STDIO:
            _error('Укажите -o', ' при чтении из stdin')
            return False
        output = source.with_suffix('.docx')
    content = _read(source)
    if content is None:
        return False

    dotenv = Path.cwd() / '.mgost' / '.env'
    can_prompt = source != STDIO
    if not can_prompt and ApiKeyHolder.stored(dotenv) is None:
        _error(
            'Токен не найден',
            f': задайте {ApiKeyHolder.API_TOKEN_KEY} или {dotenv}'
        )
        return False
    api_key = ApiKeyHolder(dotenv)
    async with ArtichaAPI(api_key.api_key) as api:
        if not await _token_valid(api, api_key, can_prompt):
            return False
        _offer_saving(api_key)
        label = 'stdin' if source == STDIO else source.name
        result = await _post(api, content, label)
        if result is None:
            return False
        print_build_result(result)
        if not (result.finished or result.running):
            _error('Документ не создан', '')
            return False
        document = await _wait_output(api)
    if document is None:
        return False
    _write(output, document)
    return True


def _error(highlighted: str, rest: str) -> None:
    Console.echo(highlighted, fg='red').echo(rest).nl()


def _read(source: Path) -> bytes | None:
    if source == STDIO:
        return sys.stdin.buffer.read()
    if not source.is_file():
        _error('Файл не найден', f': {source}')
        return None
    return source.read_bytes()


async def _token_valid(
    api: ArtichaAPI, api_key: ApiKeyHolder, can_prompt: bool
) -> bool:
    if can_prompt:
        return await token_valid(api, api_key)
    Console.echo('Валидация токена ...').edit()
    token_info = await api.validate_token()
    if isinstance(token_info, str):
        _error('Токен некорректен', f': {token_info}')
        return False
    return True


def _offer_saving(api_key: ApiKeyHolder) -> None:
    if api_key.source is not API_KEY_SOURCE.PROMPT:
        return
    if not Console.is_prompts:
        return
    if Console.confirm(
        f'Сохранить токен в {api_key.path_dotenv}?', default=False
    ):
        api_key.save()


async def _post(
    api: ArtichaAPI, content: bytes, label: str
) -> FastConversionResult | None:
    """POSTs `content`, retrying once when the server is busy"""
    for attempt in range(2):
        Console.echo('Конвертация ').echo(label, fg='cyan').echo(' ...').edit()
        try:
            return await api.fast_convert(content)
        except TimeoutException:
            _error(
                'Сервер не ответил', f' за {api.RENDER_TIMEOUT:.0f} с'
            )
            return None
        except HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code != 409:
                _error('Ошибка конвертации', f' №{status_code}')
                return None
            detail = _detail(e)
        if attempt == 0:
            Console\
                .echo('Сервер занят', fg='yellow')\
                .echo(f'{detail}. Повтор через {POLL_INTERVAL:.0f} с')\
                .nl()
            await sleep(POLL_INTERVAL)
    _error('Сервер занят', f'{detail}. Попробуйте позже')
    return None


def _detail(error: HTTPStatusError) -> str:
    try:
        return f": {error.response.json()['detail']}"
    except (ValueError, KeyError, TypeError):
        return ''


async def _wait_output(api: ArtichaAPI) -> bytes | None:
    """Downloads the document once the server stops answering 409"""
    started = monotonic()
    Console.echo('Скачивание документа ...').edit()
    while True:
        try:
            return await api.fast_convert_output()
        except HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code != 409:
                _error('Не смог скачать документ', f': ошибка №{status_code}')
                return None
        elapsed = monotonic() - started
        if elapsed >= api.RENDER_TIMEOUT:
            _error(
                'Рендер не завершился',
                f' за {api.RENDER_TIMEOUT:.0f} с. Документ можно скачать'
                ' на сайте позже'
            )
            return None
        Console\
            .echo('Рендер продолжается на сервере: ')\
            .echo(f'{elapsed:.0f} с', fg='yellow')\
            .edit()
        await sleep(POLL_INTERVAL)


def _write(output: Path, document: bytes) -> None:
    if output == STDIO:
        sys.stdout.buffer.write(document)
        sys.stdout.buffer.flush()
        Console.echo('Документ записан в stdout').nl()
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output.parent / f'.{output.name}.mgost-tmp'
    try:
        temp_path.write_bytes(document)
        replace(temp_path, output)
    finally:
        temp_path.unlink(missing_ok=True)
    Console.echo('Документ сохранён: ').echo(str(output), fg='green').nl()

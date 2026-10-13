from logging import ERROR, WARNING
from typing import TYPE_CHECKING

from mgost.api import ArtichaAPI
from mgost.api.schemas.mgost import BuildResult
from mgost.console import Console
from mgost.settings import ApiKeyHolder

if TYPE_CHECKING:
    from .mgost import MGost

__all__ = ('print_build_result', 'project_valid', 'token_valid')


async def token_valid(api: ArtichaAPI, api_key_cl: ApiKeyHolder) -> bool:
    Console.echo('Валидация токена ...').edit()
    token_info = await api.validate_token()
    while isinstance(token_info, str):
        if not Console.is_prompts:
            return False
        Console\
            .echo('Токен некорректен: ', fg="red")\
            .echo(token_info, fg="bright_red")\
            .nl()
        key = api_key_cl.api_key
        api_key_cl.remove_current_key()
        try:
            api_key_cl.load_api_key()
        except KeyboardInterrupt:
            Console\
                .nl()\
                .echo("Старый токен возвращён")\
                .nl()
            api_key_cl.api_key = key
            raise
        api.set_token(api_key_cl.api_key)
        token_info = await api.validate_token()
    return True


def _incorrect_project() -> None:
    Console\
        .echo("Текущий проект ")\
        .echo("недействительный", fg="red")\
        .echo(" в облаке.")\
        .nl()\
        .echo("Воспользуйтесь ")\
        .echo('mgost init', italic=True, underline=True)\
        .echo(' для инициализации проекта.')\
        .force_nl()


async def project_valid(mgost: 'MGost') -> bool:
    assert mgost.api is not None
    Console.echo('Валидация проекта ...').edit()
    if mgost.info.settings.project_id is None:
        _incorrect_project()
        return False
    project_id = mgost.info.settings.project_id
    if not await mgost.api.is_project_available(project_id):
        _incorrect_project()
        return False
    project = await mgost.api.project(project_id)
    Console\
        .echo("Текущий проект: ")\
        .echo(project.name, fg='green')\
        .force_nl()
    mgost.info.settings.project_name = project.name
    return True


def print_build_result(result: BuildResult) -> None:
    Console.echo('Рендер ')
    ended = 'завершён' if result.finished else 'не завершён'
    if result.max_log_level < WARNING:
        Console\
            .echo('успешно', fg='green')\
            .echo(f' {ended}')
    elif result.max_log_level < ERROR:
        Console\
            .echo(f'{ended} ')\
            .echo('с предупреждениями', fg='yellow')
    else:
        Console\
            .echo(f'{ended} ')\
            .echo('с ошибками', fg='red')
    if not result.logs:
        Console.echo(' без сообщений')
    Console.nl()
    for entry in result.logs:
        if entry.level < WARNING:
            Console.echo('ИНФО'.rjust(14), fg='white')
        elif entry.level < ERROR:
            Console.echo('ПРЕДУПРЕЖДЕНИЕ'.rjust(14), fg='yellow')
        else:
            Console.echo('ОШИБКА'.rjust(14), fg='red')
        Console\
            .echo(': ')\
            .echo(entry.message)\
            .nl()

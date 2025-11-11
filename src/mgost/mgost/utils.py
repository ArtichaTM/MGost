from typing import TYPE_CHECKING

from mgost.console import Console

if TYPE_CHECKING:
    from .mgost import MGost

__all__ = ('token_valid', 'project_valid')


async def token_valid(mgost: 'MGost') -> bool:
    assert mgost.api is not None
    Console.echo('Валидация токена ...').edit()
    token_info = await mgost.api.validate_token()
    while isinstance(token_info, str):
        Console\
            .echo('Токен некорректен: ', fg="red")\
            .echo(token_info, fg="bright_red")\
            .nl()
        api_key_cl = mgost.info.api_key
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
        token_info = await mgost.api.validate_token()
    return True


def _incorrect_project() -> None:
    Console\
        .echo("Текущий проект ")\
        .echo("недействительный", fg="red")\
        .echo(" в облаке. Воспользуйтесь ")\
        .echo('mgost init', fg='cyan')\
        .echo(' для инициализации проекта')\
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

from importlib import metadata as importlib_metadata
from pathlib import Path

from mgost.api.remote_version import get_remote_version
from mgost.console import Console
from mgost.mgost import MGost
from mgost.mgost.sync import SyncError
from mgost.mgost.utils import project_valid, token_valid

__all__ = ('version', 'token', 'init', 'sync', 'render')


async def version():
    version = importlib_metadata.version('mgost')
    Console\
        .echo("MGost версии ")\
        .echo(version, fg="green")\
        .nl()\
        .echo('Проверка новой версии...')\
        .nl()\

    remote_version = get_remote_version()
    if remote_version is None:
        Console\
            .edit()\
            .echo("Таймаут, pypi недоступен")\
            .finalize()
        return
    if version == remote_version:
        Console\
            .edit()\
            .echo(
                "У вас самая последняя версия",
                fg="green"
            )\
            .finalize()
    else:
        Console\
            .edit()\
            .echo("Есть более новая версия ")\
            .echo(
                remote_version,
                fg="yellow"
            )\
            .nl()\
            .echo("Обновите, используя команду ")\
            .echo("uvx mgost@latest", fg='cyan')\
            .nl()\
            .finalize()


async def token(
    root_path: Path
):
    mgost = MGost(root_path)
    async with mgost:
        is_token_valid = await token_valid(mgost)
        if is_token_valid is False:
            return
        token_info = await mgost.api.me()
    Console\
        .edit()\
        .echo("Токен создан ")\
        .echo(f"{token_info.created:%d.%m.%y}", fg="green")\
        .echo(" в ")\
        .echo(f"{token_info.created:%H:%M}", fg="green")\
        .echo(" пользователем ")\
        .echo(f"{token_info.owner}", fg="cyan")
    if token_info.expires is not None:
        Console\
            .echo(" и истекает ")\
            .echo(f"{token_info.modified:%d.%m.%y %H:%M}.", fg="green")\
            .nl()
    else:
        Console.echo('.').nl()
    Console.nl().finalize()


async def init(
    root_path: Path
):
    mgost = MGost(root_path)
    async with mgost:
        is_token_valid = await token_valid(mgost)
        if is_token_valid is False:
            return
        await mgost.init()
    Console.nl().finalize()


async def sync(
    root_path: Path
):
    mgost = MGost(root_path)
    async with mgost:
        is_token_valid = await token_valid(mgost)
        if is_token_valid is False:
            return
        is_project_valid = await project_valid(mgost)
        if not is_project_valid:
            return
        try:
            await mgost.sync_files()
        except SyncError:
            Console.nl().finalize()
            return


async def render(
    root_path: Path
):
    mgost = MGost(root_path)
    async with mgost:
        is_token_valid = await token_valid(mgost)
        if is_token_valid is False:
            return
        is_project_valid = await project_valid(mgost)
        if not is_project_valid:
            return
        try:
            await mgost.sync_files()
        except SyncError:
            Console.nl().finalize()
            return
        await mgost.render()

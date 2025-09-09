from importlib.metadata import version
from pathlib import Path

import typer

from mgost.console import Console
from mgost.mgost import MGost
from mgost.mgost.sync import SyncError
from mgost.mgost.utils import project_valid, token_valid

__all__ = ('app', )


app = typer.Typer(
    name="MGost",
)


@app.command(
    "version",
    help="Displays app version"
)
def _():
    Console\
        .echo("MGost версии ")\
        .echo(version('mgost'), fg="green")\
        .nl()\
        .finalize()


@app.command(
    "token",
    help="Displays token"
)
def _(
    root_path: Path = typer.Option(
        Path('.'),
        '--root', '-r',
        help="Путь к папке с проектом"
    )
):
    mgost = MGost(root_path)
    with mgost:
        is_token_valid = token_valid(mgost)
        if is_token_valid is False:
            return
        token_info = mgost.api.me()
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


@app.command(
    "init",
    help="Подготавливает директорию к новому проекту"
)
def _(
    root_path: Path = typer.Option(
        Path('.'),
        '--root', '-r',
        help="Путь к папке с проектом"
    )
):
    mgost = MGost(root_path)
    with mgost:
        is_token_valid = token_valid(mgost)
        if is_token_valid is False:
            return
        mgost.init()


@app.command(
    "sync",
    help="Синхронизирует проект с сервером без рендера"
)
def _(
    root_path: Path = typer.Option(
        Path('.'),
        '--root', '-r',
        help="Путь к папке с проектом"
    )
):
    mgost = MGost(root_path)
    with mgost:
        is_token_valid = token_valid(mgost)
        if is_token_valid is False:
            return
        is_project_valid = project_valid(mgost)
        if not is_project_valid:
            return
        try:
            mgost.sync_files()
        except SyncError:
            Console.finalize()
            return


@app.command(
    "render",
    help="Начинает рендер проекта"
)
def _(
    root_path: Path = typer.Option(
        Path('.'),
        '--root', '-r',
        help="Путь к папке с проектом"
    )
):
    mgost = MGost(root_path)
    with mgost:
        is_token_valid = token_valid(mgost)
        if is_token_valid is False:
            return
        is_project_valid = project_valid(mgost)
        if not is_project_valid:
            return
        try:
            mgost.sync_files()
        except SyncError:
            Console.finalize()
            return
        mgost.render()

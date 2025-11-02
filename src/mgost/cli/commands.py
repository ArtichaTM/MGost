from asyncio import run
from pathlib import Path

import typer

from . import async_commands
from .app import app


@app.command(
    "version",
    help="Displays app version"
)
def _():
    run(async_commands.version())


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
    run(async_commands.token(root_path))


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
    run(async_commands.init(root_path))


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
    run(async_commands.sync(root_path))


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
    run(async_commands.render(root_path))

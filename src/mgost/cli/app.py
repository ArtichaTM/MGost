from importlib.metadata import version
from pathlib import Path

import typer

from mgost.mgost import MGost

__all__ = ('app', )


app = typer.Typer(
    name="MGost",
)


@app.command(
    "version",
    help="Displays app version"
)
def _():
    typer.echo(f"MGost версии {version('mgost')}")


@app.command("build", help="Builds project")
def _(
    root_path: Path = typer.Option(  # type: ignore
        Path('.'),
        '--root', '-r',
        help="Путь к папке с проектом"
    )
):
    mgost = MGost(root_path)
    with mgost:
        mgost.build()

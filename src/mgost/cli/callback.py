from logging import getLogger

import typer

from mgost.settings.logger import init_logging

from .app import app

logger = getLogger()


@app.callback()
def main(
    ctx: typer.Context,
    v: int = typer.Option(
        None,
        "-v",
        count=True,
        help="Increase verbosity (-v).",
    ),
    quiet: bool = typer.Option(
        False,
        "-q",
        "--quiet",
        help="Quiet output",
    ),
    silent: bool = typer.Option(
        False,
        "--silent",
        help="Silent output.",
    ),
):
    if silent:
        verbosity = -2
    elif quiet:
        verbosity = -1
    elif v is not None:
        assert isinstance(v, int)
        verbosity = v
    else:
        verbosity = 0
    init_logging(verbosity)

    # logger.debug(f"Verbosity: {verbosity}")

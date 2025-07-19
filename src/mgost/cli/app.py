from pathlib import Path
from tomllib import load

from typer import Typer

__all__ = ('app', )


app = Typer(name="MGost")


@app.command()
def no_command():
    path_pyproject = (
        Path(__file__)
        .parent
        .parent
        .parent
        .parent
        .joinpath('pyproject.toml')
    )
    if not path_pyproject.exists():
        print("MGost api app")
    with path_pyproject.open('rb') as f:
        pyproject = load(f)
        project = pyproject['project']
        name = project["name"]
        version = project['version']
    print(f"{name} version {version}")

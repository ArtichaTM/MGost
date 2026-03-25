import typer

__all__ = ('app', )


app = typer.Typer(
    name="MGost",
)

def main():
    """Replaces typer callable to catch KeyboardInterrupt"""
    try:
        app()
    except KeyboardInterrupt:
        return

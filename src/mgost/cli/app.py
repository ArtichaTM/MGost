import typer

__all__ = ('app', )


app = typer.Typer(
    name="MGost",
    epilog="AI agents: https://articha.ru/static/mgost_conv/llms.md",
)

def main():
    """Replaces typer callable to catch KeyboardInterrupt"""
    try:
        app()
    except KeyboardInterrupt:
        return

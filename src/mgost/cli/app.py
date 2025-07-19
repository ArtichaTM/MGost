from typer import Typer


__all__ = ('app', )


app = Typer()


@app.command()
def xz():
    print('Q')

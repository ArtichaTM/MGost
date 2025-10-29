import typing as t

import typer
from click.types import Choice

__all__ = ('Console',)


class _Console():
    __slots__ = (
        '_r',
        '_new_line',
        '_force_new_line'
    )
    _r: bool
    _new_line: bool
    _force_new_line: bool

    class _VariablesApply:
        __slots__ = ()

        def __enter__(self) -> None:
            assert not (Console._r and Console._new_line)
            if Console._force_new_line:
                typer.echo()
            elif Console._r:
                typer.echo('\r', nl=False)
            elif Console._new_line:
                typer.echo()

        def __exit__(self, *_) -> None:
            Console._force_new_line = False
            Console._r = False
            Console._new_line = False

    def __init__(self) -> None:
        self._new_line = False
        self._r = False
        self._force_new_line = False

    def echo[T: _Console](
        self: T,
        text: str,
        fg: int | tuple[int, int, int] | str | None = None,
        bg: int | tuple[int, int, int] | str | None = None,
        bold: bool | None = None,
        dim: bool | None = None,
        underline: bool | None = None,
        overline: bool | None = None,
        italic: bool | None = None,
        blink: bool | None = None,
        reverse: bool | None = None,
        strikethrough: bool | None = None,
        reset: bool = True,
    ) -> T:
        assert isinstance(text, str)
        assert '\n' not in text
        with self._VariablesApply():
            typer.echo(typer.style(
                text,
                fg=fg,
                bg=bg,
                bold=bold,
                dim=dim,
                underline=underline,
                overline=overline,
                italic=italic,
                blink=blink,
                reverse=reverse,
                strikethrough=strikethrough,
                reset=reset
            ), nl=False)
        return self

    def edit[T: _Console](self: T) -> T:
        if self._force_new_line:
            return self
        self._r = True
        self._new_line = False
        return self

    def nl[T: _Console](self: T) -> T:
        self._r = False
        self._new_line = True
        return self

    def force_nl[T: _Console](self: T) -> T:
        self._r = False
        self._new_line = False
        self._force_new_line = True
        return self

    def prompt(
        self,
        text: str,
        default: t.Any | None = None,
        hide_input: bool = False,
        confirmation_prompt: bool | str = False,
        type: t.Any | None = None,
        value_proc: t.Callable[[str], t.Any] | None = None,
        prompt_suffix: str = ": ",
        show_default: bool = True,
        err: bool = False,
        show_choices: bool = True,
        choices: tuple[str] | tuple[int] | None = None,
    ) -> t.Any:
        with self._VariablesApply():
            value = typer.prompt(
                text=text,
                default=default,
                hide_input=hide_input,
                confirmation_prompt=confirmation_prompt,
                type=Choice(choices) if choices else type,
                value_proc=value_proc,
                prompt_suffix=prompt_suffix,
                show_default=show_default,
                err=err,
                show_choices=show_choices
            )
        return value

    def confirm(
        self,
        text: str,
        default: bool | None = False,
        abort: bool = False,
        prompt_suffix: str = ": ",
        show_default: bool = True,
        err: bool = False,
    ) -> bool:
        with self._VariablesApply():
            value = typer.confirm(
                text=text,
                default=default,
                abort=abort,
                prompt_suffix=prompt_suffix,
                show_default=show_default,
                err=err
            )
        return value

    def finalize(self) -> None:
        with self._VariablesApply():
            pass


Console = _Console()

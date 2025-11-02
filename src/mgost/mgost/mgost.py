from logging import ERROR, WARNING
from pathlib import Path

from httpx import HTTPStatusError
from rich.progress import Progress

from mgost.api import APIRequestError, ArtichaAPI
from mgost.api.schemas.mgost import BuildResult
from mgost.console import Console
from mgost.settings import MGostInfo

from .sync import sync, sync_file
from .utils import project_valid


class MGost:
    __slots__ = (
        '_root_path',
        '_info',
        '_api',
        '_last_line_length'
    )
    _root_path: Path
    _info: MGostInfo | None
    _api: ArtichaAPI | None

    def __init__(
        self,
        root_path: Path
    ) -> None:
        self._root_path = root_path
        self._info = None
        self._api = None

    async def __aenter__[T: MGost](self: T) -> T:
        assert self._info is None
        self._info = MGostInfo.load(self._root_path / '.mgost')
        self._api = ArtichaAPI(self._info.api_key.api_key)
        await self._api.__aenter__()
        return self

    async def __aexit__(self, *_):
        assert self._info is not None
        assert self._api is not None
        self._info.save(self._root_path / '.mgost')
        await self._api.__aexit__()

    @property
    def info(self) -> MGostInfo:
        assert self._info is not None, "MGost should be"\
            " initialized as context manager"
        return self._info

    @property
    def api(self) -> ArtichaAPI:
        assert self._api is not None, "MGost should be"\
            " initialized as context manager"
        return self._api

    async def sync_files(self) -> None:
        return await sync(self)

    async def sync_file(self, project_id: int, path: Path):
        assert isinstance(project_id, int)
        assert isinstance(path, Path)
        return await sync_file(self, project_id, path)

    async def render(self) -> None:
        Console.echo("Начинаю рендер").nl()
        assert self.info.settings.project_id is not None
        try:
            result = await self.api.render(self.info.settings.project_id)
        except HTTPStatusError as e:
            Console\
                .echo('Не смог выполнить рендер в виду ошибки №')\
                .echo(str(e.response.status_code), fg='red')\
                .nl()
            return
        assert isinstance(result, BuildResult)
        Console.echo('Рендер ')
        ended = 'завершён' if result.finished else 'не завершён'
        if result.max_log_level < WARNING:
            Console\
                .echo('успешно', fg='green')\
                .echo(f' {ended}')
        elif result.max_log_level < ERROR:
            Console\
                .echo(f'{ended} ')\
                .echo('с предупреждениями', fg='yellow')
        else:
            Console\
                .echo(f'{ended} ')\
                .echo('с ошибками', fg='red')
        if not result.logs:
            Console.echo(' без сообщений')
        Console.nl()
        for entry in result.logs:
            if entry.level < WARNING:
                Console.echo('ИНФО'.rjust(14), fg='white')
            elif entry.level < ERROR:
                Console.echo('ПРЕДУПРЕЖДЕНИЕ'.rjust(14), fg='yellow')
            else:
                Console.echo('ОШИБКА'.rjust(14), fg='red')
            Console\
                .echo(': ')\
                .echo(entry.message)\
                .nl()
        if result.finished:
            project = await self.api.project(
                self.info.settings.project_id
            )
            Console\
                .echo('Скачивание документа')
            try:
                with Progress() as progress:
                    await self.api.download(
                        project.id, project.path_to_docx,
                        overwrite_ok=True,
                        progress=progress
                    )
            except KeyboardInterrupt:
                Console\
                    .nl()\
                    .echo('Операция прервана пользователем')\
                    .nl()

    async def _pick_project_name(self) -> None:
        if self.info.settings.project_name is None:
            name = Console.prompt("Имя проекта")
            self.info.settings.project_name = name
        name = self.info.settings.project_name
        assert isinstance(name, str)
        Console.echo("Создаю проект...").nl()
        try:
            project_id = await self.api.create_project(name)
        except APIRequestError as e:
            if e.response.status_code != 409:  # Conflict
                raise
        else:
            Console\
                .edit()\
                .echo('Проект ')\
                .echo(name, fg="green")\
                .echo(' создан!')\
                .nl()
            self.info.settings.project_id = project_id
            return

        # Conflict in project name
        sync_project = Console\
            .edit()\
            .echo('Проект с названием ')\
            .echo(name, fg="green")\
            .echo(' ')\
            .echo('уже существует', bold=True)\
            .echo('.')\
            .nl()\
            .prompt('Синхронизировать проект с ним?')
        if not sync_project:
            self.info.settings.project_name = None
            return
        projects = await self.api.projects()
        assert projects
        for project in projects:
            if project.name == name:
                break
        else:
            Console\
                .echo("Облако сообщает о конфликте имён, ")\
                .echo('однако проекта с таким именем ')\
                .echo('не существует', fg='red')\
                .echo('.')\
                .nl()
            return
        self.info.settings.project_id = project.id

    async def init(self) -> None:
        if await project_valid(self):
            Console\
                .echo("Проект уже создан и готов к работе.")\
                .nl()\
                .echo("Используйте ")\
                .echo("mgost render", fg="cyan")\
                .echo(" для рендера проекта")\
                .nl()
            return
        projects = await self.api.projects()
        mapping = {i: proj for i, proj in enumerate(projects, 1)}
        Console\
            .nl()\
            .echo('Создать новый проект или ')\
            .echo('синхронизировать', fg='blue')\
            .echo(' существующий?')\
            .nl()
        Console\
            .echo('0. ', fg='blue')\
            .echo('Создать новый проект')\
            .nl()
        for index, project in mapping.items():
            Console\
                .echo(f'{index}. ', fg='blue')\
                .echo(f'"{project.name}"')\
                .nl()
        choices = (0, *mapping.keys())
        assert isinstance(choices, tuple)
        assert all((isinstance(i, int) for i in choices))
        value = Console.prompt(
            'Действие',
            choices=choices,  # type: ignore
            show_choices=False
        )
        if value != 0:
            project = mapping[value]
            self.info.settings.project_id = project.id
            self.info.settings.project_name = project.name
            Console\
                .nl()\
                .echo("Выбран проект ")\
                .echo(f"{project.name}", fg='green')\
                .echo(".")\
                .force_nl()
            return
        Console\
            .edit()\
            .echo('Начинаю создание проекта в папке "')\
            .echo(str(self._root_path.resolve().name), fg="green")\
            .echo('"')\
            .nl()
        while True:
            await self._pick_project_name()
            if self.info.settings.project_name:
                break
        md_path = self._root_path / 'main.md'
        replace_md = True
        if md_path.exists():
            answer = Console\
                .echo("Файл ")\
                .echo(str(md_path), fg="green")\
                .echo(" уже существует. ")\
                .confirm("Заменить его?")
            replace_md = answer

        if replace_md:
            example = await self.api.download_example()
            md_path.write_bytes(example)
            assert self.info.settings.project_id is not None
            await self.api.upload(
                self.info.settings.project_id,
                md_path, overwrite=False
            )

        Console\
            .echo('Проект "')\
            .echo(f'{self.info.settings.project_name}', fg='green')\
            .echo('" инициализирован.')\
            .nl()\
            .echo('Используйте ')\
            .echo('mgost sync', fg='blue')\
            .echo('для синхронизации проекта')

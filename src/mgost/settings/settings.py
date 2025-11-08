import enum
import json
from os import environ, getenv
from pathlib import Path

from dotenv import dotenv_values

from mgost.console import Console

__all__ = (
    'MGostInfo',
    'Settings',
)


class API_KEY_SOURCE(enum.IntEnum):
    ENV = enum.auto()
    DOTENV = enum.auto()
    PROMPT = enum.auto()


class Settings:
    __slots__ = (
        'project_id',
        'project_name',
        'md_path',
        'docx_path'
    )
    project_id: int | None
    project_name: str | None
    md_path: Path | None
    docx_path: Path | None

    def __init__(
        self,
        project_id: int | None = None,
        project_name: str | None = None,
        md_path: Path | None = None,
        docx_path: Path | None = None
    ) -> None:
        super().__init__()
        assert project_id is None or isinstance(project_id, int)
        assert project_name is None or isinstance(project_name, str)
        assert md_path is None or isinstance(md_path, str)
        assert docx_path is None or isinstance(docx_path, str)
        self.project_id = project_id
        self.project_name = project_name
        self.md_path = Path(md_path) if md_path else None
        self.docx_path = Path(docx_path) if docx_path else None

    @classmethod
    def from_dict[T: Settings](
        cls: type[T], dictionary: dict
    ) -> T:
        return cls(**dictionary)

    def to_dict(self) -> dict:
        output = dict()
        if self.project_id is not None:
            output['project_id'] = self.project_id
            output['project_name'] = self.project_name
            output['md_path'] = str(self.md_path)
            output['docx_path'] = str(self.docx_path)
        return output


class ApiKeyHolder:
    API_TOKEN_KEY = 'ARTICHAAPI_TOKEN'
    __slots__ = (
        'path_dotenv',
        'api_key',
        'source'
    )
    path_dotenv: Path
    api_key: str
    source: API_KEY_SOURCE

    def __init__(self, path_dotenv: Path) -> None:
        assert isinstance(path_dotenv, Path)
        self.path_dotenv = path_dotenv
        self.load_api_key()

    def load_api_key(self) -> None:
        env_token = getenv(self.API_TOKEN_KEY)
        if env_token is not None:
            self.source = API_KEY_SOURCE.ENV
            self.api_key = env_token
            return

        if self.path_dotenv.exists():
            dotenv = dotenv_values(self.path_dotenv)
            dotenv_token = dotenv.get(self.API_TOKEN_KEY)
            if dotenv_token is not None:
                self.source = API_KEY_SOURCE.DOTENV
                self.api_key = dotenv_token
                return

        Console\
            .echo("API ключ ")\
            .echo("не найден", fg="red")\
            .echo(" ни в переменных среды, ни в .env.")\
            .nl()
        Console\
            .echo(
                "Введите код вручную или внесите его в "
                "вышеперечисленные источники"
            )\
            .nl()
        value = Console.prompt(self.API_TOKEN_KEY, prompt_suffix='=')
        self.source = API_KEY_SOURCE.PROMPT
        self.api_key = value

    def remove_current_key(self) -> None:
        match self.source:
            case API_KEY_SOURCE.PROMPT:
                pass
            case API_KEY_SOURCE.DOTENV:
                lines = self.path_dotenv.read_text().split('\n')
                self.path_dotenv.write_text(
                    '\n'.join(i for i in lines if not i.startswith(
                        self.API_TOKEN_KEY
                    ))
                )
                environ.pop(self.API_TOKEN_KEY, default=None)
            case API_KEY_SOURCE.ENV:
                del environ[self.API_TOKEN_KEY]

    def save(self) -> None:
        if self.source is not API_KEY_SOURCE.PROMPT:
            return
        if not self.path_dotenv.parent.exists():
            self.path_dotenv.parent.mkdir(exist_ok=False)
        with self.path_dotenv.open('w') as f:
            f.write(f"{self.API_TOKEN_KEY}={self.api_key}")


class MGostInfo:
    __slots__ = (
        'settings',
        'api_key'
    )
    settings: Settings
    api_key: ApiKeyHolder

    def __init__(
        self,
        settings: dict | None = None,
        /,
        path_dotenv: Path | None = None
    ) -> None:
        if settings is None:
            settings = dict()
        self.settings = Settings.from_dict(settings)
        assert isinstance(path_dotenv, Path)
        self.api_key = ApiKeyHolder(path_dotenv)

    @staticmethod
    def _load_json(path: Path) -> dict:
        if not path.exists():
            return dict()
        with path.open('r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def _save_json(obj: dict, path: Path, indent: int | None = None) -> None:
        assert isinstance(obj, dict)
        assert isinstance(path, Path)
        assert isinstance(indent, int) or indent is None
        if not path.parent.exists():
            return
        with path.open('w', encoding='utf-8') as f:
            json.dump(obj, f, indent=indent)

    @classmethod
    def load[T: MGostInfo](cls: type[T], path: Path) -> T:
        """Loads settings from a `.mgost` folder"""
        path_dotenv = path / '.env'
        if not path.exists():
            return cls(path_dotenv=path_dotenv)
        return cls(
            cls._load_json(path / 'settings.json'),
            path_dotenv=path_dotenv
        )

    def save(self, path: Path):
        """Saves current state of settings into a folder"""
        self.api_key.save()
        settings = self.settings.to_dict()
        if not settings:
            return
        if not path.exists():
            path.mkdir(parents=False, exist_ok=False)
        if settings:
            self._save_json(settings, path / 'settings.json', indent=4)

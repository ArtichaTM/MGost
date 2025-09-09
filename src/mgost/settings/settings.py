import enum
import json
from abc import ABC, abstractmethod
from datetime import datetime
from os import getenv
from pathlib import Path

from dotenv import dotenv_values

from mgost.console import Console

__all__ = (
    'MGostInfo',
    'FileInfo',
    'Settings',
)


class API_KEY_SOURCE(enum.IntEnum):
    ENV = enum.auto()
    DOTENV = enum.auto()
    PROMPT = enum.auto()


class DictBasedClass(ABC):
    @classmethod
    def from_dict(cls, dictionary: dict):
        return cls(**dictionary)

    @abstractmethod
    def to_dict(self) -> dict:
        raise NotImplementedError()


class FileInfo(DictBasedClass):
    __slots__ = (
        'path',
        'date_upload'
    )

    def __init__(
        self,
        path: str,
        date_upload: float
    ) -> None:
        super().__init__()
        assert isinstance(path, str)
        assert isinstance(date_upload, (float | int))
        self.path = Path(path)
        self.date_upload = datetime.fromtimestamp(date_upload)

    def to_dict(self) -> dict:
        return {
            'path': str(self.path),
            'date_upload': self.date_upload.timestamp()
        }


class Settings(DictBasedClass):
    __slots__ = (
        'project_id',
        'project_name',
    )
    project_id: int | None
    project_name: str | None

    def __init__(
        self,
        project_id: int | None = None,
        project_name: str | None = None
    ) -> None:
        super().__init__()
        self.project_id = project_id
        self.project_name = project_name

    def to_dict(self) -> dict:
        output = dict()
        if self.project_id is not None:
            output['project_id'] = self.project_id
            output['project_name'] = self.project_name
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
        self.api_key = self._load_api_key()

    def _load_api_key(self) -> str:
        env_token = getenv(self.API_TOKEN_KEY)
        if env_token is not None:
            self.source = API_KEY_SOURCE.ENV
            return env_token

        if self.path_dotenv.exists():
            dotenv = dotenv_values(self.path_dotenv)
            dotenv_token = dotenv.get(self.API_TOKEN_KEY)
            if dotenv_token is not None:
                self.source = API_KEY_SOURCE.DOTENV
                return dotenv_token

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
        return value

    def save(self) -> None:
        if self.source is not API_KEY_SOURCE.PROMPT:
            return
        if not self.path_dotenv.parent.exists():
            self.path_dotenv.parent.mkdir(exist_ok=False)
        with self.path_dotenv.open('w') as f:
            f.write(f"{self.API_TOKEN_KEY}={self.api_key}")


class MGostInfo:
    __slots__ = (
        'files',
        'settings',
        'api_key'
    )
    files: dict[str, FileInfo]
    settings: Settings
    api_key: ApiKeyHolder

    def __init__(
        self,
        files: dict[str, dict] | None = None,
        settings: dict | None = None,
        /,
        path_dotenv: Path | None = None
    ) -> None:
        if files is None:
            files = dict()
        if settings is None:
            settings = dict()
        self.files = {
            k: FileInfo.from_dict(v) for k, v in files.items()
        }
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
            cls._load_json(path / 'files.json'),
            cls._load_json(path / 'settings.json'),
            path_dotenv=path_dotenv
        )

    def save(self, path: Path):
        """Saves current state of settings into a folder"""
        self.api_key.save()
        files = {k: v.to_dict() for k, v in self.files.items()}
        settings = self.settings.to_dict()
        if not (files or settings):
            return
        if not path.exists():
            path.mkdir(parents=False, exist_ok=False)
        if files:
            self._save_json(files, path / 'files.json')
        if settings:
            self._save_json(settings, path / 'settings.json', indent=4)

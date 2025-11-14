from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import respx


@dataclass(slots=True, frozen=True)
class _RoutesFileMethods:
    put: dict[Path, respx.Route] = field(default_factory=dict)
    post: dict[Path, respx.Route] = field(default_factory=dict)
    patch: dict[Path, respx.Route] = field(default_factory=dict)
    delete: dict[Path, respx.Route] = field(default_factory=dict)
    get: dict[Path, respx.Route] = field(default_factory=dict)

    def methods(self) -> Iterable[str]:
        return self.__dataclass_fields__.keys()

    def route_dict(
        self,
        method: str
    ) -> dict[Path, respx.Route]:
        assert method.lower() == method
        assert method in self.methods()
        method_route = getattr(self, method)
        return method_route


@dataclass(slots=True, frozen=True)
class _RoutesFile:
    existing: _RoutesFileMethods = field(default_factory=_RoutesFileMethods)
    new: _RoutesFileMethods = field(default_factory=_RoutesFileMethods)

    def types(self) -> Iterable[str]:
        return self.__dataclass_fields__.keys()

    def route_dict(
        self,
        method: str,
        type: str
    ) -> dict[Path, respx.Route]:
        assert type.lower() == type
        assert type in self.types()
        routes_file = getattr(self, type)
        assert isinstance(routes_file, _RoutesFileMethods)
        return routes_file.route_dict(method)


@dataclass(slots=True, frozen=False)
class Routes:
    _projects: respx.Route | None = None
    _project: respx.Route | None = None
    _project_files: respx.Route | None = None
    _project_requirements: respx.Route | None = None
    _project_render: respx.Route | None = None
    file: _RoutesFile = field(default_factory=_RoutesFile)

    @property
    def projects(self) -> respx.Route:
        assert self._projects is not None
        return self._projects

    @property
    def project(self) -> respx.Route:
        assert self._project is not None
        return self._project

    @property
    def project_files(self) -> respx.Route:
        assert self._project_files is not None
        return self._project_files

    @property
    def project_requirements(self) -> respx.Route:
        assert self._project_requirements is not None
        return self._project_requirements

    @property
    def project_render(self) -> respx.Route:
        assert self._project_render is not None
        return self._project_render

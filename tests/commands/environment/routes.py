from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, Iterable

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

    def _yield_routes(self) -> Generator[respx.Route, None, None]:
        for method in self.methods():
            dictionary = getattr(self, method)
            assert isinstance(dictionary, dict)
            for route in dictionary.values():
                assert isinstance(route, respx.Route)
                yield route


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

    def _yield_routes(self) -> Generator[respx.Route, None, None]:
        for type in self.types():
            routes_file = getattr(self, type)
            assert isinstance(routes_file, _RoutesFileMethods)
            yield from routes_file._yield_routes()


@dataclass(slots=True, frozen=False)
class Routes:
    _projects: respx.Route | None = None
    _project: respx.Route | None = None
    _project_put: respx.Route | None = None
    _project_files: respx.Route | None = None
    _project_requirements: respx.Route | None = None
    _project_render: respx.Route | None = None
    _examples: respx.Route | None = None
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
    def project_put(self) -> respx.Route:
        assert self._project_put is not None
        return self._project_put

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

    @property
    def examples(self) -> respx.Route:
        assert self._examples is not None
        return self._examples

    def _yield_routes(self) -> Generator[respx.Route, None, None]:
        yield self.project
        yield self.project_files
        yield self.project_render
        yield self.project_requirements
        yield self.projects
        yield from self.file._yield_routes()

    def assert_all_not_called_except(
        self,
        *routes: respx.Route
    ) -> None:
        should_be_called = {route.pattern for route in routes}
        for route in self._yield_routes():
            assert isinstance(route, respx.Route)
            if route.pattern in should_be_called:
                assert route.called, (
                    f"Route is not called when should: {route}"
                )
            else:
                assert not route.called, (
                    f"Route is called when should not: {route}"
                )

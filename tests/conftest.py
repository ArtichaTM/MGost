from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
import respx

from mgost.mgost import MGost

from .harness import FakeCloud, Workspace


@dataclass(frozen=True, slots=True)
class Clock:
    """Fixed clock. Whole seconds only, so timestamps survive the
    datetime -> float -> st_mtime -> datetime round trip exactly."""

    now: datetime

    @property
    def second_ago(self) -> datetime:
        return self.now - timedelta(seconds=1)

    @property
    def seconds2_ago(self) -> datetime:
        return self.now - timedelta(seconds=2)

    def ago(self, **kwargs) -> datetime:
        return self.now - timedelta(**kwargs)

    def ahead(self, **kwargs) -> datetime:
        return self.now + timedelta(**kwargs)


@pytest.fixture
def clock() -> Clock:
    return Clock(datetime.now(timezone.utc).replace(microsecond=0))


@pytest.fixture(autouse=True)
def _api_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets a token before any MGost/ArtichaAPI is constructed.

    The old suite monkeypatched this inline, after MGost() was built —
    an ordering dependency that happened to work.
    """
    monkeypatch.setenv('ARTICHAAPI_TOKEN', '1')


@pytest.fixture
def cloud(respx_mock: respx.MockRouter):
    store = FakeCloud(respx_mock)
    yield store
    store.close()


@pytest.fixture
def workspace():
    store = Workspace(prefix='workspace-')
    yield store
    store.close()


@pytest.fixture
def sync_project(workspace: Workspace, cloud: FakeCloud):
    """Runs `mgost sync` against the fixture project.

    Replaces the eight lines that were copy-pasted into all ten sync
    tests of the old suite.
    """
    async def _run() -> None:
        mgost = MGost(workspace.root)
        async with mgost:
            mgost.info.settings.project_id = cloud.project_id
            mgost.info.settings.project_name = cloud.name
            await mgost.sync_files()

    return _run


@pytest.fixture
def render_project(workspace: Workspace, cloud: FakeCloud):
    async def _run() -> None:
        mgost = MGost(workspace.root)
        async with mgost:
            mgost.info.settings.project_id = cloud.project_id
            mgost.info.settings.project_name = cloud.name
            await mgost.render()

    return _run

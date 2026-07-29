from datetime import timezone
from pathlib import Path

import pytest

from tests.harness import FileStore, Workspace, filler


@pytest.fixture
def store():
    s = FileStore(prefix='test-')
    yield s
    s.close()


def test_materialise_writes_size_and_mtime(store, clock):
    store.materialise(Path('a/b.md'), size=20, modified=clock.second_ago)
    assert store.stat(Path('a/b.md')).st_size == 20
    assert store.modified(Path('a/b.md')) == clock.second_ago


def test_paths_are_relative(store, clock):
    store.materialise(Path('a/b.md'), size=1, modified=clock.now)
    store.materialise(Path('c.md'), size=1, modified=clock.now)
    assert store.paths() == {Path('a/b.md'), Path('c.md')}


def test_filler_is_deterministic_and_sized():
    assert filler(Path('x.md'), 350_000) == filler(Path('x.md'), 350_000)
    assert filler(Path('x.md'), 64) != filler(Path('y.md'), 64)
    assert len(filler(Path('x.md'), 0)) == 0
    assert len(filler(Path('x.md'), 350_000)) == 350_000


def test_move_and_remove(store, clock):
    store.materialise(Path('a.md'), size=5, modified=clock.now)
    store.move(Path('a.md'), Path('sub/b.md'))
    assert store.paths() == {Path('sub/b.md')}
    store.remove(Path('sub/b.md'))
    assert store.paths() == set()


def test_close_is_idempotent(store):
    store.close()
    store.close()


def test_mtime_survives_roundtrip_exactly(store, clock):
    """Guards the datetime -> float -> stat -> datetime conversion."""
    store.materialise(
        Path('a.md'), size=1, modified=clock.ago(days=1, seconds=1)
    )
    assert store.modified(Path('a.md')) == clock.ago(days=1, seconds=1)
    assert store.modified(Path('a.md')).tzinfo is timezone.utc


@pytest.fixture
def workspace_store():
    w = Workspace(prefix='ws-')
    yield w
    w.close()


def test_mgost_directory_is_pruned_including_nested(workspace_store, clock):
    ws = workspace_store
    ws.materialise(Path('main.md'), size=1, modified=clock.now)
    ws.materialise(Path('.mgost/settings.json'), size=1, modified=clock.now)
    ws.materialise(
        Path('.mgost/nested/deep/.env'), size=1, modified=clock.now
    )
    assert ws.paths() == {Path('main.md')}


def test_assert_converged_passes_on_identical_stores(workspace_store, clock):
    other = FileStore(prefix='other-')
    try:
        for store in (workspace_store, other):
            store.materialise(
                Path('main.md'), size=20, modified=clock.second_ago
            )
        workspace_store.assert_converged(other)
    finally:
        other.close()


def test_assert_converged_reports_missing_paths(workspace_store, clock):
    other = FileStore(prefix='other-')
    try:
        other.materialise(
            Path('main.md'), size=20, modified=clock.second_ago
        )
        with pytest.raises(AssertionError, match='main.md'):
            workspace_store.assert_converged(other)
    finally:
        other.close()


def test_assert_converged_reports_size_drift(workspace_store, clock):
    other = FileStore(prefix='other-')
    try:
        workspace_store.materialise(
            Path('main.md'), size=20, modified=clock.second_ago
        )
        other.materialise(
            Path('main.md'), size=21, modified=clock.second_ago
        )
        with pytest.raises(AssertionError, match='size'):
            workspace_store.assert_converged(other)
    finally:
        other.close()


def test_assert_converged_reports_mtime_drift(workspace_store, clock):
    other = FileStore(prefix='other-')
    try:
        workspace_store.materialise(
            Path('main.md'), size=20, modified=clock.second_ago
        )
        other.materialise(Path('main.md'), size=20, modified=clock.now)
        with pytest.raises(AssertionError, match='mtime'):
            workspace_store.assert_converged(other)
    finally:
        other.close()

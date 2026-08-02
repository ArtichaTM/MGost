from datetime import datetime
from hashlib import sha256
from pathlib import Path

from mgost.api.schemas.mgost import ProjectFile
from mgost.mgost.matching import (
    Match, Matcher, collect_candidates, file_digest
)


def test_digest_matches_hashlib(workspace, clock):
    workspace.materialise(Path('main.md'), size=20, modified=clock.now)
    full = workspace.root / 'main.md'

    assert file_digest(full) == sha256(full.read_bytes()).hexdigest()


def test_collects_nested_files(workspace, clock):
    workspace.materialise(Path('a.md'), size=1, modified=clock.now)
    workspace.materialise(Path('docs/b.md'), size=2, modified=clock.now)

    found = collect_candidates(workspace.root, tracked=())

    assert set(found) == {Path('a.md'), Path('docs/b.md')}
    assert found[Path('docs/b.md')].size == 2


def test_prunes_hidden_directories_recursively(workspace, clock):
    """The old skip only dropped files sitting directly in a dotted
    directory, so .git/objects/ab/x still reached the comparison."""
    workspace.materialise(Path('.git/config'), size=1, modified=clock.now)
    workspace.materialise(
        Path('.git/objects/ab/x'), size=1, modified=clock.now
    )
    workspace.materialise(Path('main.md'), size=1, modified=clock.now)

    found = collect_candidates(workspace.root, tracked=())

    assert set(found) == {Path('main.md')}


def test_excludes_tracked_paths(workspace, clock):
    workspace.materialise(Path('main.md'), size=1, modified=clock.now)
    workspace.materialise(Path('notes.md'), size=1, modified=clock.now)

    found = collect_candidates(workspace.root, tracked=(Path('notes.md'),))

    assert set(found) == {Path('main.md')}


def test_records_mtime_as_aware_utc(workspace, clock):
    workspace.materialise(Path('main.md'), size=1, modified=clock.now)

    found = collect_candidates(workspace.root, tracked=())

    assert found[Path('main.md')].modified == clock.now
    assert found[Path('main.md')].modified.tzinfo is not None


def cloud_file(path: Path, data: bytes, modified: datetime) -> ProjectFile:
    return ProjectFile(
        project_id=1,
        path=path.as_posix(),
        created=modified,
        modified=modified,
        size=len(data),
        hash=sha256(data).hexdigest(),
    )


def test_pass1_matches_identical_bytes(workspace, clock):
    data = b'x' * 20
    (workspace.root / 'docs').mkdir()
    workspace.write(Path('docs/main.md'), data, clock.seconds2_ago)
    missing = {Path('main.md'): cloud_file(
        Path('main.md'), data, clock.second_ago
    )}

    matcher = Matcher(
        workspace.root, collect_candidates(workspace.root, tracked=())
    )

    assert matcher.resolve(missing) == [
        Match(Path('main.md'), Path('docs/main.md'), rung=1)
    ]


def test_pass1_ignores_empty_files(workspace, clock):
    """Every empty file has the same digest, so size 0 carries no
    identity."""
    workspace.write(Path('unrelated.txt'), b'', clock.seconds2_ago)
    missing = {Path('main.md'): cloud_file(
        Path('main.md'), b'', clock.second_ago
    )}

    matcher = Matcher(
        workspace.root, collect_candidates(workspace.root, tracked=())
    )

    assert matcher.resolve(missing) == []


def test_pass1_ignores_equal_size_different_bytes(workspace, clock):
    workspace.write(Path('unrelated.txt'), b'y' * 20, clock.seconds2_ago)
    missing = {Path('main.md'): cloud_file(
        Path('main.md'), b'x' * 20, clock.second_ago
    )}

    matcher = Matcher(
        workspace.root, collect_candidates(workspace.root, tracked=())
    )

    assert matcher.resolve(missing) == []


def test_pass1_claims_each_candidate_once(workspace, clock):
    """Two cloud files with identical content must not both claim the
    same local file."""
    data = b'x' * 20
    workspace.write(Path('one.md'), data, clock.seconds2_ago)
    missing = {
        Path('a.md'): cloud_file(Path('a.md'), data, clock.second_ago),
        Path('b.md'): cloud_file(Path('b.md'), data, clock.second_ago),
    }

    matcher = Matcher(
        workspace.root, collect_candidates(workspace.root, tracked=())
    )
    matches = matcher.resolve(missing)

    assert len(matches) == 1
    assert matches[0].local_path == Path('one.md')


def test_pass1_prefers_the_matching_basename(workspace, clock):
    """Two byte-identical candidates: the one keeping the name wins, and
    the choice must not depend on filesystem order."""
    data = b'x' * 20
    workspace.write(Path('zzz/other.md'), data, clock.seconds2_ago)
    workspace.write(Path('aaa/main.md'), data, clock.seconds2_ago)
    missing = {Path('main.md'): cloud_file(
        Path('main.md'), data, clock.second_ago
    )}

    matcher = Matcher(
        workspace.root, collect_candidates(workspace.root, tracked=())
    )

    assert matcher.resolve(missing) == [
        Match(Path('main.md'), Path('aaa/main.md'), rung=1)
    ]


def test_pass2_matches_surviving_basename(workspace, clock):
    workspace.write(Path('docs/main.md'), b'edited!' * 3, clock.now)
    missing = {Path('main.md'): cloud_file(
        Path('main.md'), b'x' * 20, clock.second_ago
    )}

    matcher = Matcher(
        workspace.root, collect_candidates(workspace.root, tracked=())
    )

    assert matcher.resolve(missing) == [
        Match(Path('main.md'), Path('docs/main.md'), rung=2)
    ]


def test_pass2_declines_two_candidates_sharing_a_name(workspace, clock):
    """The several-markdown-files case: ambiguous, so download."""
    workspace.write(Path('docs/main.md'), b'a' * 21, clock.now)
    workspace.write(Path('archive/main.md'), b'b' * 22, clock.now)
    missing = {Path('main.md'): cloud_file(
        Path('main.md'), b'x' * 20, clock.second_ago
    )}

    matcher = Matcher(
        workspace.root, collect_candidates(workspace.root, tracked=())
    )

    assert matcher.resolve(missing) == []


def test_pass2_is_case_sensitive(workspace, clock):
    workspace.write(Path('docs/Main.md'), b'a' * 21, clock.now)
    missing = {Path('main.md'): cloud_file(
        Path('main.md'), b'x' * 20, clock.second_ago
    )}

    matcher = Matcher(
        workspace.root, collect_candidates(workspace.root, tracked=())
    )

    assert matcher.resolve(missing)[0].rung == 3


def test_pass3_matches_the_sole_remainder(workspace, clock):
    workspace.write(Path('chapter.md'), b'a' * 21, clock.now)
    missing = {Path('main.md'): cloud_file(
        Path('main.md'), b'x' * 20, clock.second_ago
    )}

    matcher = Matcher(
        workspace.root, collect_candidates(workspace.root, tracked=())
    )

    assert matcher.resolve(missing) == [
        Match(Path('main.md'), Path('chapter.md'), rung=3)
    ]


def test_pass3_declines_when_two_remain_on_either_side(workspace, clock):
    workspace.write(Path('one.txt'), b'a' * 21, clock.now)
    workspace.write(Path('two.txt'), b'b' * 22, clock.now)
    missing = {Path('main.md'): cloud_file(
        Path('main.md'), b'x' * 20, clock.second_ago
    )}

    matcher = Matcher(
        workspace.root, collect_candidates(workspace.root, tracked=())
    )

    assert matcher.resolve(missing) == []


def test_passes_run_in_order(workspace, clock):
    """An exact match must not be consumed by pass 2 or 3."""
    data = b'x' * 20
    workspace.write(Path('docs/main.md'), data, clock.seconds2_ago)
    workspace.write(Path('chapter.md'), b'a' * 21, clock.now)
    missing = {
        Path('main.md'): cloud_file(Path('main.md'), data, clock.second_ago),
        Path('other.md'): cloud_file(
            Path('other.md'), b'z' * 30, clock.second_ago
        ),
    }

    matcher = Matcher(
        workspace.root, collect_candidates(workspace.root, tracked=())
    )
    by_cloud = {m.cloud_path: m for m in matcher.resolve(missing)}

    assert by_cloud[Path('main.md')] == Match(
        Path('main.md'), Path('docs/main.md'), rung=1
    )
    assert by_cloud[Path('other.md')] == Match(
        Path('other.md'), Path('chapter.md'), rung=3
    )

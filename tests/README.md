# Tests

Run: `uv run pytest`. CI also runs `uv run pytest -n 2`, so no test may
depend on execution order.

## Layout

- `harness/` — the test doubles. `FileStore` is a real directory with a
  temp dir behind it; `Workspace` and `FakeCloud` both extend it. They
  differ only in that `FakeCloud` also answers HTTP through respx.
- `conftest.py` — `clock`, `cloud`, `workspace`, `sync_project`.
- `commands/test_sync.py` — the scenario table below.

Assertions read `cloud.file_calls()`, a sorted list of `Call` records the
file handler appends to itself. There is no route registry to keep in step
with the tests, which is what the previous harness got wrong.

Paths are `pathlib.Path` everywhere, including inside `Call`. `Path`
equality and ordering are identical on every platform; `str(Path('a/b'))`
is `a\b` on Windows, and CI runs Windows. Conversion to `str` happens only
in JSON payloads and URLs, via `.as_posix()`.

## Scenario table

| # | local | cloud | condition | expect |
|---|---|---|---|---|
| 1 | yes | no | — | `POST` |
| 2 | no | yes | nothing similar in tree | `GET` |
| 3a | no | yes | same name + same size elsewhere | `PATCH` |
| 3b | no | yes | same name + different size elsewhere | `GET` |
| 4a | no | yes | unrelated file, equal size, 0 B | `GET` |
| 4b | no | yes | unrelated file, equal size, ~64 B | `GET` |
| 4c | no | yes | unrelated file, equal size, ~350 KB | `GET` |
| 5 | yes | yes | Δmtime < 1s | no file calls |
| 6 | yes | yes | local newer | `PUT` |
| 7 | yes | yes | cloud newer | `GET` |
| 8 | yes | yes | Δmtime = 1 day + 1s | `PUT` |
| 10 | no | no | requirement missing everywhere | no file calls |

Rows 7 and 8 guard a bug fixed in `7fa24a0`: `timedelta.seconds` is never
negative, so a −1s delta reported `86399` and the cloud-newer branch was
unreachable; it also drops the days component, returning `0` at exactly one
day. The sizes in 4a–4c match `_file_chunker`'s `chunk_size=65536`: 0 B
produces no chunks at all, 64 B one partial chunk, 350 KB five full chunks
plus a remainder.

## Known failures

Five rows fail on purpose. They assert intended behaviour that `src/` does
not implement, and are left plain red — no `xfail`, no `skip` — so the bugs
stay visible.

| row | scenario | expected | actual |
|---|---|---|---|
| 3a | decoy with the right name and size | `PATCH` | `AssertionError` |
| 3b | decoy with the right name, wrong size | `GET` | `AssertionError` |
| 4a | unrelated decoy, both files empty | `GET` | `AssertionError` |
| 4b | unrelated decoy, equal size (64 B) | `GET` | `AssertionError` |
| 4c | unrelated decoy, equal size (350 KB) | `GET` | `AssertionError` |

All five die in the same place, before any HTTP call is made:

```
src/mgost/mgost/sync.py:290:  in sync
src/mgost/mgost/sync.py:240:  in _sync_non_requirements_file
src/mgost/mgost/sync.py:131:  in sync_file
                              return FileMovedLocally(
src/mgost/api/actions.py:59:  in __post_init__
                              assert not self.path.is_absolute()
E                             AssertionError

self = FileMovedLocally(
    root_path=PosixPath('/tmp/workspace-hud7tecf'),
    project_id=1,
    path=PosixPath('/tmp/workspace-hud7tecf/main.md'),
    new_path=PosixPath('unrelated.txt'),
)
```

### Cause 1 — the move branch cannot be constructed

`sync_file`'s `(local, cloud) = (absent, present)` branch builds
`FileMovedLocally(mgost.project_root, project_id, full_path, new_path)`
(`sync.py:131`), where `full_path` is `project_root / path` and therefore
absolute. `PathAction.__post_init__` asserts `not self.path.is_absolute()`.
Every other construction site passes the relative `path`; only this one
passes `full_path`.

The whole branch is therefore dead: the moment `_search_file` finds any
candidate for a cloud-only file, sync aborts with `AssertionError` instead
of moving anything. Row 3a is the *intended* behaviour — a genuine move —
and it crashes too, which is why five rows are red rather than the four
originally predicted.

This was never caught before because the old suite had no case where a
cloud-only file had a local look-alike.

### Cause 2 — masked behind cause 1

Once the constructor is fixed, 3b/4a/4b/4c should still fail, for two
reasons in `_search_file` / `_compare_file_to` in `src/mgost/mgost/sync.py`:

1. `_compare_file_to` returns `True` on a name match alone. Its guard tests
   `path.suffix not in {'md', 'docx', 'xlsx'}`, but `suffix` yields `'.md'`
   *with* the dot, so the dotless set never matches, the early `return
   True` always fires, and the comparison below it is unreachable.
2. Below that, matching falls through to size alone, because the
   `st_birthtime` check is skipped on any platform lacking the attribute.

Neither is observable from the test output today; both were read from the
source. Expect `['PATCH'] != ['GET']` on those four rows once cause 1 is
resolved.

## Deferred decisions

### Equal mtime, different size

Sync ignores size entirely in the `(local, cloud) = (present, present)`
branch: within the one-second dead band it does nothing, whatever the
sizes. Reaching that state takes deliberate effort — roughly 0.1% of users
— so it is not a table row. Row 9 is skipped in the numbering to hold its
place.

Intended resolution: an "ask" branch that questions the user before acting,
rather than silently choosing a direction.

### Missing requirement warnings

When the markdown references a file present neither locally nor in the
cloud, the server already emits a warning during render. Sync may warn
locally too, but the two must not duplicate. Row 10 therefore asserts only
that no file request is made, and says nothing about console output.

### File identity across platforms

`_search_file` gates rename detection on `st_birthtime`, which exists on
macOS/BSD and on Windows under CPython 3.12+, but **not on Linux** — and no
platform lets you *set* it, so it cannot be used as a fixture either. The
CI matrix is ubuntu + windows + macos, so move detection currently takes a
different code path per OS.

Signals available from `ProjectFile` (`path`, `created`, `modified`,
`size`):

| signal | survives move | survives rename | portable |
|---|---|---|---|
| name | yes | no | yes |
| size | yes | yes | yes |
| mtime | yes | yes | yes |
| birthtime | yes | yes | no |

Proposed rule:

```
same_file := size == cloud.size
             AND (name == cloud.name OR mtime == cloud.modified)
```

A move keeps the name, so name+size identifies it. A rename changes the
name, so mtime+size does — the mtime still equals the cloud's `modified`
if the file was not edited since the last sync. Anything else downloads.

Two signals are required because the costs are asymmetric: a false positive
`PATCH`es the cloud into the wrong shape, a false negative merely
re-downloads. The durable fix is a server-provided content hash on
`ProjectFile` — only bytes truly identify a file.

Tests never set cloud `created` to a real local birth instant, so the
birthtime branch stays dead on all three platforms and the suite behaves
identically everywhere.

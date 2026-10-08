# Tests

Run: `uv run pytest`. CI also runs `uv run pytest -n 2`, so no test may
depend on execution order.

## Layout

- `harness/` — the test doubles. `FileStore` is a real directory with a
  temp dir behind it; `Workspace` and `FakeCloud` both extend it. They
  differ only in that `FakeCloud` also answers HTTP through respx.
- `conftest.py` — `clock`, `cloud`, `workspace`, `sync_project`.
- `commands/test_sync.py` — the scenario table below.
- `commands/test_sync_external.py` — rows 14–20, files outside the project.

Assertions read `cloud.file_calls()`, a sorted list of `Call` records the
file handler appends to itself. There is no route registry to keep in step
with the tests, which is what the previous harness got wrong.

The server addresses files by id. `FakeCloud` assigns an ordinary file its
id on first sight (`cloud.id_of(path)`) and keeps it across a `PATCH`, yet
`Call` still records the path, so the tables below read by path. A
fictional file is seeded with `cloud.add_fictional(written, …)`, stored
under `.fictional/<id>`, hidden from `cloud.paths()`, and recorded as
`Path(written)`. In `cloud.requirements` a `Path` is an ordinary
requirement and a `str` is sent exactly as written.

Paths are `pathlib.Path` everywhere, including inside `Call`. `Path`
equality and ordering are identical on every platform; `str(Path('a/b'))`
is `a\b` on Windows, and CI runs Windows. Conversion to `str` happens only
in JSON payloads and URLs, via `.as_posix()`.

## Scenario table

Rows 3a–4c and 11–13 exercise the identity matcher (`mgost/matching.py`):
is a local file, present at some other path, the same file as a cloud
file with no local file at its own path?

| # | local candidate | `name` eq | bytes eq | pass | expect |
|---|---|---|---|---|---|
| 1 | — | — | — | — | `POST` |
| 2 | *(none)* | — | — | — | `GET` |
| 3a | `docs/main.md` | yes | yes | 1 | `PATCH` |
| 3b | `docs/main.md`, cloud newer | yes | no | 2 | `PATCH`, `GET` |
| 3c | `docs/main.md`, local newer | yes | no | 2 | `PATCH`, `PUT` |
| 4a | `unrelated.txt`, equal size, 0 B | no | yes | — | `GET` |
| 4b | `unrelated.txt`, equal size, ~64 B | no | no | — | `GET` |
| 4c | `unrelated.txt`, equal size, ~350 KB | no | no | — | `GET` |
| 11 | `notes.md`, itself a cloud file | no | yes | — | `GET` |
| 12 | `docs/main.md` and `archive/main.md` | yes ×2 | no | — | `GET` |
| 13 | `chapter.md`, sole remainder | no | no | 3 | confirmed: `PATCH`, `PUT`; unattended: `GET` |

Rows 5, 6, 7, 8 and 10 exercise the both-present and
missing-everywhere branches instead, and are unrelated to file identity:

| # | cloud `main.md` | local `main.md` | expect |
|---|---|---|---|
| 5 | 20 B, `t−1s` | 20 B, `t−1s` or `t−0.5s` | no file calls |
| 6 | 20 B, `t−1s` | 21 B, `t` | `PUT` |
| 7 | 21 B, `t` | 20 B, `t−1s` | `GET` |
| 8 | 20 B, `t−1 day` | 21 B, `t` | `PUT` |
| 10 | requirement `ghost.png` nowhere | — | no file calls |

Rows 14–20 cover requirements outside the project: absolute, or climbing
out with `..`. The server stores them as fictional files keyed by the
written path. Sync only uploads them and never writes outside the project;
to edit such a file through the cloud, copy it into the project. Nothing is
searched for: one stat at the written path decides presence, and an
absolute path for the other OS counts as missing locally.

| # | external file | expect |
|---|---|---|
| 14 | local only | `POST ?path=<written>` |
| 15 | both, bytes differ, local newer | `PUT` |
| 16 | both, bytes differ, cloud newer | `PUT`, warns the cloud copy was newer |
| 17 | both, bytes equal | no file calls |
| 18 | cloud only: deleted locally, or other-OS path | no file calls, notes the cloud copy is used |
| 19 | absolute path inside the project | `POST` as fictional, warns to write it relative, not a move candidate |
| 20 | nowhere | no file calls |

Row 19 keeps the absolute path fictional because the server keys the file
by the written string; uploading it as ordinary would leave the
requirement without a `file_id` until the markdown is rewritten.

Rows 7 and 8 guard a bug fixed in `7fa24a0`: `timedelta.seconds` is never
negative, so a −1s delta reported `86399` and the cloud-newer branch was
unreachable; it also drops the days component, returning `0` at exactly one
day. The sizes in 4a–4c match `_file_chunker`'s `chunk_size=65536`: 0 B
produces no chunks at all, 64 B one partial chunk, 350 KB five full chunks
plus a remainder.

The suite is fully green — no `xfail`, no `skip`, no known failures.

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

Identity is settled by the server-provided SHA-256 digest on
`ProjectFile.hash`, not by `st_birthtime` — which exists on macOS/BSD and
on Windows under CPython 3.12+, but not on Linux, and cannot be set on any
platform, so it could never have been used as a fixture either. The
matcher (`mgost/matching.py`) runs three passes over the whole set of
missing cloud files and unclaimed local candidates, most-evidence first:

1. **Exact digest.** `size > 0 ∧ size == cloud.size ∧ sha256 == cloud.hash`
   — moved, not edited. No prompt.
2. **Surviving basename.** Exactly one unclaimed candidate shares the
   cloud file's name — moved and edited. Prompts, defaults to yes, takes
   yes unattended.
3. **Sole remainder.** Exactly one missing cloud file and one unclaimed
   candidate left, with different sizes — moved, renamed and edited.
   Prompts, defaults to yes, but **declines unattended**: it is pure
   arity with no content evidence, so nobody watching must not become
   "PATCH something over an unrelated file."

Bytes are the only signal that truly identifies a file, which is why this
replaces the old two-signal (name, size) heuristic entirely rather than
adding a third signal to it.

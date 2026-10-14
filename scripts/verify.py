# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Local mirror of .github/workflows, one line per step: `make verify`.

A step's own output is shown only when it fails; the first failure stops the run.
"""

import os
import subprocess
import sys
from pathlib import Path

STEPS: list[tuple[str, list[str]]] = [
    ("lock", ["uv", "lock", "--check"]),
    ("ruff", ["uv", "run", "--locked", "ruff", "check"]),
    ("ty", ["uv", "run", "--locked", "ty", "check"]),
    ("isort", ["uv", "run", "--locked", "isort", "--check-only", "--diff", "."]),
    ("test", ["uv", "run", "--locked", "pytest", "-q"]),
]

ROOT = Path(__file__).resolve().parent.parent
COLOR = sys.stdout.isatty()
# `uv run` sets VIRTUAL_ENV to this script's env; steps must use the project .venv
ENV = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}


def status(ok: bool) -> None:
    text = "ok" if ok else "FAILED"
    if COLOR:
        text = f"\033[{32 if ok else 31}m{text}\033[0m"
    print(text, flush=True)


def step(name: str, command: list[str]) -> bool:
    print(f"{name}... ", end="", flush=True)
    result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT, env=ENV)
    status(result.returncode == 0)
    if result.returncode != 0:
        print(result.stdout + result.stderr, end="")
    return result.returncode == 0


passed = all(step(name, command) for name, command in STEPS)
print("verify... ", end="")
status(passed)
sys.exit(0 if passed else 1)

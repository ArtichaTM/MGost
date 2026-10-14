#!/usr/bin/env bash
# dev -> main release: fast-forward main, run `make verify` on it, push; roll back on failure.
#
# git has no hook for a fast-forward merge, so the check wraps the merge instead. After the
# fast-forward main's worktree equals dev, so verify sees exactly what is about to be pushed.
set -euo pipefail

DEV=dev
MAIN=main

function fail {
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

cd "$(git rev-parse --show-toplevel)"

branch=$(git rev-parse --abbrev-ref HEAD)
[ "$branch" = "$DEV" ] || fail "on '$branch', expected '$DEV'"

# `git reset --hard` without an argument would reset to the merged commit and undo nothing.
base=$(git rev-parse --verify "$MAIN")

echo "> Switching to $MAIN"
git checkout "$MAIN"

echo "> Fast-forwarding $MAIN to $DEV"
if ! git merge --ff-only "$DEV"
then
    git checkout "$DEV"
    fail "$MAIN cannot fast-forward to $DEV - it has commits of its own"
fi

echo "> Verifying"
if ! make verify
then
    echo "> Rolling $MAIN back to $base"
    git reset --hard "$base"
    git checkout "$DEV"
    fail "verify failed on $MAIN - nothing was pushed"
fi

echo "> Pushing $MAIN"
git push || fail "push failed - $MAIN is merged locally but unpushed, and you are on it"

echo "> Switching back to $DEV"
git checkout "$DEV"

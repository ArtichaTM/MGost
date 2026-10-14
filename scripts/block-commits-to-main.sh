#!/usr/bin/env bash
# pre-commit hook: commits go to dev; main only moves through `make merge-main`.
set -e

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo DETACHED)

case "$branch" in
    main|master)
        echo "ERROR: direct commits to '$branch' are disabled; commit to dev and run 'make merge-main'." >&2
        echo "Override once with: git commit --no-verify" >&2
        exit 1
        ;;
esac

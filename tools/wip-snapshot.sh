#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# When a session ends with work it never committed, keep a copy of that work in git -- without
# touching the files, the index or the branch.
#
# Several sessions work in this repository at once, each in a worktree of its own, and a worktree
# whose session has ended is easy to forget and easy to delete. What dies with it is whatever was
# never committed. So the session's end runs this (.claude/settings.json, SessionEnd): if anything
# in the checkout differs from HEAD, it is written as a commit that no branch points at, under
# refs/wip/<branch>/<when>. Those refs live in the repository's one shared .git, so they survive the
# worktree folder being removed; tools/dev.sh checkouts lists them, and
#
#   git switch -c rescued refs/wip/<branch>/<when>      or      git checkout refs/wip/<branch>/<when> -- <path>
#
# brings the work back. A copy of the index is used to stage it, so the checkout is left exactly as
# the session left it, and files .gitignore names are not taken.
#
# It never fails a session's exit: anything unexpected, and it says nothing and stops.
set -u

input=$(cat 2>/dev/null || true)
dir=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("cwd") or "")' 2>/dev/null || true)
[ -n "$dir" ] || dir=${CLAUDE_PROJECT_DIR:-$PWD}
cd "$dir" 2>/dev/null || exit 0
top=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$top" || exit 0
[ -n "$(git status --porcelain --untracked-files=all 2>/dev/null)" ] || exit 0

branch=$(git branch --show-current 2>/dev/null); [ -n "$branch" ] || branch=detached
index=$(mktemp "${TMPDIR:-/tmp}/wip-index.XXXXXX") || exit 0
trap 'rm -f "$index"' EXIT
# Start from a copy of the real index, so staging the copy is quick and the real one is never written.
cp "$(git rev-parse --git-path index)" "$index" 2>/dev/null || rm -f "$index"
GIT_INDEX_FILE="$index" git add -A -- . >/dev/null 2>&1 || exit 0
tree=$(GIT_INDEX_FILE="$index" git write-tree 2>/dev/null) || exit 0
head=$(git rev-parse -q --verify HEAD 2>/dev/null || true)
[ -n "$head" ] && [ "$tree" = "$(git rev-parse -q --verify "HEAD^{tree}")" ] && exit 0

when=$(date +%Y%m%d-%H%M%S)
msg="Not committed when a session in $(basename "$top") on $branch ended, $(date '+%Y-%m-%d %H:%M')"
commit=$(git commit-tree "$tree" ${head:+-p "$head"} -m "$msg" 2>/dev/null) || exit 0
ref="refs/wip/$branch/$when"
git update-ref -m "$msg" "$ref" "$commit" 2>/dev/null || exit 0
printf '{"systemMessage": "Work not committed in %s was kept as %s (tools/dev.sh checkouts lists it)"}\n' "$(basename "$top")" "$ref"

#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Every checkout of this repository on this machine, and which of them hold work that would be lost.
#
#   tools/dev.sh checkouts     every worktree and loose branch, one plain word each, and what to do
#   tools/dev.sh tidy          remove what is merged and clean -- listed first, asked, nothing else
#   tools/checkouts.sh brief   the lines tools/dev.sh puts in its report: only what needs a look
#
# Several sessions work here at once, each in a worktree on its own branch. A session ends, its
# worktree is forgotten, and whatever it held goes stale or goes altogether: commits that were never
# pushed exist on this disk only, and work never committed exists in that folder only. On 5 October
# one branch held twelve commits on no remote and another had development as its upstream. So this
# reads each checkout and says one word about it:
#
#   in use          a process is working in it, or it changed in the last half hour
#   not committed   changes in it, and nobody working there
#   only here       commits that are on no remote -- push them, or they are one rm away
#   waiting         pushed, with a pull request open
#   merged          its branch is in development and it holds nothing else: tidy removes it once
#                   it has been left alone for a day
#   pushed          everything in it is on the remote
#
# The worst word wins. It reads remote-tracking refs as of the last fetch and never fetches, so the
# report stays instant; pull requests are asked of GitHub only by `checkouts`, never by `brief`.
# Work a session left uncommitted when it ended is under refs/wip/ (tools/wip-snapshot.sh), and is
# listed here until somebody deals with it.
set -uo pipefail
cd "$(dirname "$0")/.."

if [ -t 1 ]; then B=$'\033[1m'; D=$'\033[2m'; Y=$'\033[33m'; G=$'\033[32m'; R=$'\033[0m'; else B=; D=; Y=; G=; R=; fi
row() { printf "  %s%-8s%s %s\n" "$D" "$1" "$R" "$2"; }
plural() { if [ "$1" = 1 ]; then printf '%s %s' "$1" "$2"; else case "$2" in *ch|*sh|*s|*x) printf '%s %ses' "$1" "$2" ;; *) printf '%s %ss' "$1" "$2" ;; esac; fi; }

base=origin/development
git rev-parse -q --verify "$base" >/dev/null || base=development
here=$(git rev-parse --show-toplevel)
ACTIVE_SECS=1800

# Folders some process is sitting in. One lsof for the lot; half a second.
busy=$(lsof -a -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | sort -u || true)
in_use() {
  local wt=$1
  grep -qxF "$wt" <<<"$busy" || grep -q "^$wt/" <<<"$busy" && return 0
  # A session does not always sit in its folder; a checkout that changed in the last half hour is
  # somebody's, whatever lsof says.
  local gd idx now; gd=$(git -C "$wt" rev-parse --absolute-git-dir 2>/dev/null) || return 1
  now=$(date +%s)
  for f in "$gd/index" "$gd/HEAD" "$gd/logs/HEAD"; do
    [ -e "$f" ] && [ $(( now - $(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f") )) -lt $ACTIVE_SECS ] && return 0
  done
  return 1
}

idle_for() { # worktree seconds: nothing in its git dir has changed for that long
  local gd now f; gd=$(git -C "$1" rev-parse --absolute-git-dir 2>/dev/null) || return 1; now=$(date +%s)
  for f in "$gd/index" "$gd/HEAD" "$gd/logs/HEAD"; do
    [ -e "$f" ] && [ $(( now - $(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f") )) -lt "$2" ] && return 1
  done
  return 0
}

# One line per worktree: path, branch (or a commit, detached), and the facts the word is made of.
# Tab-separated: path branch ref dirty onlyhere merged busy last
facts() {
  local wt="" br="" ref="" line
  while IFS= read -r line || [ -n "$wt" ]; do
    case "$line" in
      "worktree "*) wt=${line#worktree } ;;
      "branch refs/heads/"*) br=${line#branch refs/heads/} ;;
      "HEAD "*) ref=${line#HEAD } ;;
      "")
        if [ -n "$wt" ] && [ -d "$wt" ]; then
          local r=${br:-$ref} dirty only merged busyw last
          dirty=$(git -C "$wt" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
          only=$(git rev-list --count "$r" --not --remotes 2>/dev/null || echo 0)
          git merge-base --is-ancestor "$r" "$base" 2>/dev/null && merged=1 || merged=0
          in_use "$wt" && busyw=1 || busyw=0
          last=$(git log -1 --format=%cr "$r" 2>/dev/null)
          printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$wt" "${br:-detached}" "$r" "$dirty" "$only" "$merged" "$busyw" "$last"
        fi
        wt="" br="" ref=""
        [ -z "$line" ] || break ;;
    esac
  done < <(git worktree list --porcelain; echo)
}

# The word, worst first.
word() { # dirty only merged busy pr
  if [ "$4" = 1 ]; then echo "in use"
  elif [ "$1" != 0 ]; then echo "not committed"
  elif [ "$2" != 0 ]; then echo "only here"
  elif [ "$5" = 1 ]; then echo "waiting"
  elif [ "$3" = 1 ]; then echo "merged"
  else echo "pushed"; fi
}
paint() { case "$1" in "not committed"|"only here") printf '%s%-13s%s' "$Y" "$1" "$R" ;; merged) printf '%s%-13s%s' "$G" "$1" "$R" ;; *) printf '%-13s' "$1" ;; esac; }
why() { # word dirty only last
  case "$1" in
    "not committed") echo "$(plural "$2" file) changed, nobody working there · $4" ;;
    "only here") echo "$(plural "$3" commit) on no remote · $4" ;;
    *) echo "$4" ;;
  esac
}

# Local branches no worktree has checked out, that hold commits on no remote. A branch is where a
# finished session's work most often sits after its folder is gone.
loose() {
  local out; out=$(git worktree list --porcelain | sed -n 's|^branch refs/heads/||p')
  # One walk finds every branch whose tip is on no remote; only those are counted.
  git log --branches --not --remotes --simplify-by-decoration --format='%D' 2>/dev/null | tr ',' '\n' \
    | sed -e 's/^ *//' -e 's/^HEAD -> //' | grep -v -e '^tag: ' -e '^refs/' -e '/' -e '^$' | sort -u | while read -r b; do
    git show-ref -q --verify "refs/heads/$b" || continue
    grep -qxF "$b" <<<"$out" && continue
    local n; n=$(git rev-list --count "$b" --not --remotes 2>/dev/null || echo 0)
    [ "$n" != 0 ] && printf '%s\t%s\t%s\n' "$b" "$n" "$(git log -1 --format=%cr "$b")"
  done
}

merged_branches() {
  local out; out=$(git worktree list --porcelain | sed -n 's|^branch refs/heads/||p')
  git branch --merged "$base" --format='%(refname:short)' 2>/dev/null | while read -r b; do
    case "$b" in main|development|"") continue ;; esac
    grep -qxF "$b" <<<"$out" || echo "$b"
  done
}

snapshots() { git for-each-ref --sort=-creatordate --format='%(refname:short)%09%(creatordate:relative)%09%(subject)' refs/wip/ 2>/dev/null; }

name_of() { if [ "$1" = "$here" ]; then echo "$(basename "$1") ${D}(this one)${R}"; else basename "$1"; fi; }

brief() {
  local lines=() total=0 wt br ref dirty only merged busyw last w
  while IFS=$'\t' read -r wt br ref dirty only merged busyw last; do
    [ "$wt" = "$here" ] && continue
    total=$((total + 1))
    w=$(word "$dirty" "$only" "$merged" "$busyw" 0)
    case "$w" in "not committed"|"only here") lines+=("$(printf '%-16s %-26s %s %s' "$(basename "$wt")" "$br" "$(paint "$w")" "$D$(why "$w" "$dirty" "$only" "$last")$R")") ;; esac
  done < <(facts)
  local lb=0 b n last
  while IFS=$'\t' read -r b n last; do
    [ -n "$b" ] || continue; lb=$((lb + 1))
    lines+=("$(printf '%-16s %-26s %s %s' "${D}no folder${R}" "$b" "$(paint "only here")" "$D$(plural "$n" commit) on no remote · $last$R")")
  done < <(loose)
  local snaps; snaps=$(snapshots | wc -l | tr -d ' ')
  local tidy; tidy=$(merged_branches | wc -l | tr -d ' ')
  [ "$total" = 0 ] && [ "$lb" = 0 ] && [ "$snaps" = 0 ] && return 0
  if [ ${#lines[@]} = 0 ]; then
    row "others" "$(plural "$total" other) beside this one, nothing at risk ${D}— tools/dev.sh checkouts${R}"
  else
    row "others" "${Y}$(plural ${#lines[@]} thing) at risk${R} ${D}of $(plural "$total" other) — tools/dev.sh checkouts${R}"
    for l in "${lines[@]}"; do printf '           %s\n' "$l"; done
  fi
  [ "$snaps" != 0 ] && row "kept" "${Y}$(plural "$snaps" snapshot)${R} of work a session left uncommitted ${D}— tools/dev.sh checkouts${R}"
  [ "$tidy" -gt 5 ] && row "tidy" "${D}$tidy merged branches — tools/dev.sh tidy${R}"
  return 0
}

full() {
  local prs=""
  command -v gh >/dev/null && prs=$(timeout 8 gh pr list --state open --limit 100 --json headRefName -q '.[].headRefName' 2>/dev/null || true)
  echo "${B}checkouts${R} ${D}· as of the last fetch · against $base${R}"
  local wt br ref dirty only merged busyw last w pr
  while IFS=$'\t' read -r wt br ref dirty only merged busyw last; do
    grep -qxF "$br" <<<"$prs" && pr=1 || pr=0
    w=$(word "$dirty" "$only" "$merged" "$busyw" "$pr")
    printf '  %-28s %-26s %s %s\n' "$(name_of "$wt")" "$br" "$(paint "$w")" "$D$(why "$w" "$dirty" "$only" "$last")$R"
    if [ "$w" = "in use" ] && [ "$wt" != "$here" ] && { [ "$dirty" != 0 ] || [ "$only" != 0 ]; }; then
      printf '  %-28s %s\n' "" "$D$([ "$dirty" != 0 ] && echo "$(plural "$dirty" file) not committed")$([ "$dirty" != 0 ] && [ "$only" != 0 ] && echo ', ')$([ "$only" != 0 ] && echo "$(plural "$only" commit) on no remote") — fine while it is in use$R"
    fi
  done < <(facts)
  local any=0 b n
  while IFS=$'\t' read -r b n last; do
    [ -n "$b" ] || continue
    [ $any = 0 ] && { echo; echo "${B}branches with no folder${R} ${D}· commits that are on no remote${R}"; any=1; }
    printf '  %-28s %s %s\n' "$b" "$(paint "only here")" "$D$(plural "$n" commit) · $last · git push origin $b$R"
  done < <(loose)
  local s; s=$(snapshots)
  if [ -n "$s" ]; then
    echo; echo "${B}kept when a session ended${R} ${D}· git switch -c rescued <ref> brings one back; git update-ref -d <ref> lets it go${R}"
    while IFS=$'\t' read -r ref when subj; do printf '  %-40s %s\n' "$ref" "$D$when · $subj$R"; done <<<"$s"
  fi
  local st; st=$(git stash list --format='%gd%x09%cr%x09%gs' 2>/dev/null)
  if [ -n "$st" ]; then
    echo; echo "${B}stashes${R} ${D}· git stash show -p <n> to read one; git stash branch <name> <n> to keep it${R}"
    while IFS=$'\t' read -r ref when subj; do printf '  %-12s %s\n' "$ref" "$D$when · $subj$R"; done <<<"$st"
  fi
  local m; m=$(merged_branches | wc -l | tr -d ' ')
  echo
  [ "$m" != 0 ] && echo "  ${D}$(plural "$m" branch) and every merged, clean worktree can go — tools/dev.sh tidy lists them and asks${R}"
}

# Removes only what is merged into development and holds nothing else: worktrees whose branch is in
# it, clean and with nobody working there, and branches no folder has checked out. Says which first,
# and does nothing without a yes. Unmerged work, uncommitted work, stashes and kept snapshots are not
# touched -- deciding about those is somebody's, not a sweep's.
tidy() {
  local yes=${1:-}
  local wts=() brs=() wt br ref dirty only merged busyw last
  while IFS=$'\t' read -r wt br ref dirty only merged busyw last; do
    [ "$wt" = "$here" ] && continue
    # A day untouched as well: merged and clean is also what a session looks like the minute after
    # its pull request lands, while it is still open on somebody's screen.
    [ "$merged" = 1 ] && [ "$dirty" = 0 ] && [ "$only" = 0 ] && [ "$busyw" = 0 ] && idle_for "$wt" 86400 && wts+=("$wt|$br")
  done < <(facts)
  while read -r br; do [ -n "$br" ] && brs+=("$br"); done < <(merged_branches)
  if [ ${#wts[@]} = 0 ] && [ ${#brs[@]} = 0 ]; then echo "  nothing merged to tidy"; return 0; fi
  echo "${B}merged into $base, holding nothing else${R}"
  for x in ${wts[@]+"${wts[@]}"}; do echo "  worktree  ${x%%|*}  ${D}(${x#*|})${R}"; done
  for x in ${brs[@]+"${brs[@]}"}; do echo "  branch    $x"; done
  if [ "$yes" != "--yes" ]; then
    printf '\n  Remove these? [y/N] '
    local a; read -r a </dev/tty 2>/dev/null || a=n
    [ "$a" = y ] || [ "$a" = Y ] || { echo "  left as they are"; return 0; }
  fi
  for x in ${wts[@]+"${wts[@]}"}; do git worktree remove "${x%%|*}" && echo "  removed ${x%%|*}"; done
  for x in ${brs[@]+"${brs[@]}"}; do git branch -D "$x" >/dev/null && echo "  deleted $x"; done
  for x in ${wts[@]+"${wts[@]}"}; do br=${x#*|}; [ "$br" != detached ] && git branch -D "$br" >/dev/null 2>&1 && echo "  deleted $br"; done
  git worktree prune
}

case "${1:-full}" in
  brief) brief ;;
  full|checkouts) full ;;
  tidy) shift || true; tidy "${1:-}" ;;
  *) sed -n '7,9p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac

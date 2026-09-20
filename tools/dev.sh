#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# The first command to run in this checkout, whether you have never seen it or were here last month.
#
#   tools/dev.sh          where you left it — or, in a fresh clone, what this is and what to run
#   tools/dev.sh up       install whatever is missing, then the panel on a mock house
#   tools/dev.sh hub      the panel against a real brain, started fresh so it is your code
#   tools/dev.sh check    what CI runs, here, before pushing
#   tools/dev.sh design   every artboard in a browser, on the canvas they were drawn on
#
# Two audiences, one report. Somebody coming back wants the half hour deleted that goes: which
# branch was I on, what is that uncommitted file, is that stash mine, is anything still listening on
# 8300 from Tuesday. Somebody who has just cloned wants none of that -- there is nothing to report --
# and instead wants to know what the directories are, what to run, and that it needs no hub. The
# default prints whichever of those two this checkout is.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -t 1 ]; then B=$'\033[1m'; D=$'\033[2m'; Y=$'\033[33m'; R=$'\033[0m'; else B=; D=; Y=; R=; fi
row() { printf "  %s%-8s%s %s\n" "$D" "$1" "$R" "$2"; }
n() { if [ "$1" = 1 ]; then printf '%s %s' "$1" "$2"; else printf '%s %ss' "$1" "$2"; fi; }

# The pid listening on a port, and how long it has been there. Same lsof/ps pair as brain/dev.py,
# for the same reason: a hub that has been up since this morning serves an older shape of /home and
# the panel renders it without complaint, so it reads as a panel bug rather than as a stale process.
# `|| true` on both: with pipefail on, an lsof that finds nothing is a failed pipeline, and a port
# with nothing on it is the ordinary case here rather than an error.
holder() { lsof -ti tcp:"$1" -sTCP:LISTEN 2>/dev/null | head -1 || true; }
uptime_of() { ps -o etime= -p "$1" 2>/dev/null | tr -d ' ' || true; }

# ---- what this machine needs before anything here can run -------------------------------------
# Both floors are CI's (ci.yml: python 3.13, node 22) and brain/pyproject.toml's requires-python.
# Naming the version that IS here matters more than the floor: on a Mac with pyenv or conda,
# `python3` is very often an old one that is first on PATH, and a venv built from it installs
# happily and then fails in the tests in ways that read as bugs in the code rather than as the
# wrong interpreter. So this looks past `python3` for a new enough one and says which it found.
py_version() { "$1" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || true; }
py_ok() { case "${1%%.*}.$(echo "$1" | cut -d. -f2)" in 3.1[3-9]|3.[2-9][0-9]) return 0;; *) return 1;; esac; }

PY=; PY_V=; PY_SEEN=
for c in python3.14 python3.13 python3; do
  command -v "$c" >/dev/null 2>&1 || continue
  v=$(py_version "$c"); [ -n "$v" ] || continue
  [ -n "$PY_SEEN" ] || PY_SEEN="$v"
  if py_ok "$v"; then PY=$c; PY_V=$v; break; fi
done
NODE_V=$(node -v 2>/dev/null | tr -d v || true)

prereqs() {                                # "" when this machine can build what was asked for
  local bad=                                #   prereqs panel | prereqs both
  case "${NODE_V%%.*}" in
    2[2-9]|[3-9][0-9]) ;;
    *) bad="node 22+ (found ${NODE_V:-none}) — brew install node" ;;
  esac
  if [ "${1:-both}" = both ] && [ -z "$PY" ]; then
    bad="${bad:+$bad; }python 3.13+ (found ${PY_SEEN:-none}) — brew install python@3.13"
  fi
  printf '%s' "$bad"
}

# ---- installed, and installed from the current lists -------------------------------------------
# A venv from three weeks ago against a requirements.txt from last week is the same class of problem
# as the stale hub: it runs, and what it does wrong looks like your code.
STAMP=brain/.venv/.deps
node_stale() { [ ! -d app/node_modules ] || [ app/package-lock.json -nt app/node_modules/.package-lock.json ]; }
venv_stale() { [ ! -x brain/.venv/bin/python ] || [ ! -f $STAMP ] \
               || [ brain/requirements.txt -nt $STAMP ] || [ brain/requirements-dev.txt -nt $STAMP ]; }
venv_old() { [ -x brain/.venv/bin/python ] && ! py_ok "$(py_version brain/.venv/bin/python)"; }
fresh() { node_stale && venv_stale && [ ! -d app/dist ]; }

# `ensure panel` is everything the mock house needs, and it is all node — so somebody who has just
# cloned to look at the screens is not made to wait on pip building esptool first. The brain's venv
# is built by the two commands that actually run python.
ensure() {
  local bad; bad=$(prereqs "$1")
  if [ -n "$bad" ]; then echo "${Y}this machine needs: $bad${R}" >&2; exit 1; fi
  if node_stale; then echo "${D}app: npm install${R}"; (cd app && npm install); fi
  [ "$1" = both ] || return 0
  if venv_old; then
    echo "${Y}brain/.venv is python $(py_version brain/.venv/bin/python); rebuilding it on $PY_V${R}"
    rm -rf brain/.venv
  fi
  if venv_stale; then
    echo "${D}brain: venv on python $PY_V${R}"
    [ -x brain/.venv/bin/python ] || "$PY" -m venv brain/.venv
    brain/.venv/bin/pip install -q -r brain/requirements.txt -r brain/requirements-dev.txt
    touch $STAMP
  fi
}

# ---- the fresh clone ---------------------------------------------------------------------------
# What a directory listing does not tell you, in the order it is needed. Not a tour of the project:
# README.md is that, and this says where it is rather than repeating it.
first_time() {
  echo "${B}home-hub${R} ${D}·${R} ${B}nothing installed here yet${R}"
  echo
  echo "  A smart home hub. The panel and the brain are the product; Home Assistant, Zigbee2MQTT"
  echo "  and the radios are rented plumbing that a household never sees."
  echo
  row "app/"    "the screens — one Vue app for the wall panel and the phone"
  row "brain/"  "the hub — FastAPI: the house's state, the rules, the assistant, the websocket"
  row "design/" "the artboards — what a screen should look like, before it is a screen"
  row "docs/"   "why each piece is the way it is. Read one before changing what it describes"
  echo
  local bad; bad=$(prereqs)
  if [ -n "$bad" ]; then row "needs" "${Y}$bad${R}"
  else row "needs" "node $NODE_V ${D}for the panel${R}, python $PY_V ${D}for the brain — both here${R}"; fi
  echo
  echo "  ${B}tools/dev.sh up${R} ${D}— installs the panel, then opens it on a house that is not real:${R}"
  echo "  ${D}eight rooms, lights at half, a film on the TV, three cameras. No hub, no Pi, no Home${R}"
  echo "  ${D}Assistant, no accounts, and every change to app/src/ is on the screen as you save it.${R}"
  echo
  echo "  ${D}Then: README.md#layout for what each directory does, CONTRIBUTING.md for what CI"
  echo "  checks and how commits are written, and tools/dev.sh check to run that here.${R}"
}

# ---- coming back --------------------------------------------------------------------------------
where_you_were() {
  branch=$(git rev-parse --abbrev-ref HEAD)
  echo "${B}home-hub${R} ${D}·${R} ${B}${branch}${R}"

  row "last" "$(git log -1 --format='%cr — %s' | cut -c1-72)"

  changed=$(git status --porcelain | wc -l | tr -d ' ')
  if [ "$changed" != 0 ]; then
    row "changed" "${Y}$(n "$changed" file)${R}  ${D}$(git status --porcelain | head -3 | awk '{print $NF}' | paste -sd ' ' -)${R}"
  fi

  # Unpushed work is the one thing a break really loses: it is invisible from GitHub and from any
  # other machine, and it is what "I thought I'd finished that" usually turns out to be.
  if up=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null); then
    read -r behind ahead < <(git rev-list --left-right --count "$up...HEAD")
    [ "$ahead" != 0 ] && row "unpushed" "${Y}$(n "$ahead" commit)${R} not on $up"
    [ "$behind" != 0 ] && row "behind" "$(n "$behind" commit) on $up waiting for you"
  else
    row "unpushed" "${Y}no upstream${R} — git push -u origin $branch"
  fi

  stashes=$(git stash list | wc -l | tr -d ' ')
  [ "$stashes" != 0 ] && row "stash" "${Y}${stashes}${R}  $(git stash list -1 --format='%gs' | cut -c1-60)"

  # What else was in flight. Branch names are how this project remembers a piece of work, so the
  # three most recently touched ones are most of the answer to "what was I doing".
  others=$(git for-each-ref --sort=-committerdate --format='%(refname:short) (%(committerdate:relative))' refs/heads \
           | grep -v "^${branch} " | head -3 | paste -sd '  ' - || true)
  [ -n "$others" ] && row "also" "$D$others$R"

  # Anything still running from before the break, and how old it is.
  while read -r port what; do
    pid=$(holder "$port")
    if [ -n "$pid" ]; then row ":$port" "$what ${D}pid $pid, up $(uptime_of "$pid")${R}"; fi
  done <<'PORTS'
8300 the brain
8399 the mock brain
5173 vite
8123 home assistant
8402 the artboards
PORTS

  missing=()
  [ -n "$(prereqs)" ] && missing+=("$(prereqs)")
  venv_old && missing+=("a newer python for brain/.venv")
  node_stale && missing+=("app deps")
  venv_stale && missing+=("brain deps")
  if [ ${#missing[@]} -eq 0 ]; then row "ready" "everything installed and current"
  else row "ready" "${Y}$(IFS=,; echo "${missing[*]}" | sed 's/,/, /g')${R} ${D}— tools/dev.sh up does it${R}"; fi

  echo
  echo "  ${D}tools/dev.sh up${R} — the panel on the mock brain, watched, no hub needed"
  echo "  ${D}tools/dev.sh hub${R} — the same against a real brain   ${D}tools/dev.sh check${R} — what CI runs"
  echo "  ${D}tools/dev.sh design${R} — the artboards, before any of it is code"
}

usage() { sed -n '4,10p' "$0" | sed 's/^# \{0,1\}//'; }

case "${1:-status}" in
  status|"") if fresh; then first_time; else where_you_were; fi ;;
  # Vite prints the address it actually took, so this does not guess one. PORT=8405 moves the mock
  # if something already holds :8399.
  up)    ensure panel; cd app && exec npm run dev:mock ;;
  # The boards are static HTML and the viewer is dependency-free node, so this deliberately does
  # NOT call ensure: looking at the design is the one thing here that should work in a clone
  # where nothing has been installed. Extra flags (--port, --no-open) pass straight through.
  design) shift || true; exec node tools/artboards.mjs "$@" ;;
  # dev.py stops whatever hub is holding the port and starts yours with the reloader on, so the
  # brain here is always the code you just wrote.
  hub)   ensure both
         # Both halves in their own process group (`set -m`), so one Ctrl-C — or the terminal window
         # closing — takes the brain, uvicorn's reloader, npm and vite with it. A hub still on :8300
         # tomorrow morning is the stale brain this whole script exists to save you from.
         set -m
         brain/.venv/bin/python brain/dev.py & brain=$!
         ( cd app && npm run dev ) & panel=$!
         set +m
         trap 'kill -TERM -$brain -$panel 2>/dev/null || true' INT TERM EXIT
         # One of them going down makes the other useless, so the pair lives and dies together —
         # the rule mock/dev.mjs already keeps for the mock pair, in the shell rather than in node.
         while kill -0 $brain 2>/dev/null && kill -0 $panel 2>/dev/null; do sleep 1; done ;;
  # CI's jobs, in CI's order, minus the ones that need a browser or a container. The sheet checks
  # are in here because they catch what nothing else does: a drawing changed in src/art.ts or
  # src/sky.ts and not in the design sheet generated from it.
  check) ensure both
         ( cd brain && .venv/bin/python -m ruff check . && .venv/bin/python -m pytest tests -q )
         ( cd app && npm run typecheck && npm run lint && npm test \
                  && npm run art-sheet:check && npm run weather-sheet:check )
         if [ -d matter-bridge/node_modules ]; then ( cd matter-bridge && npm run check && npm test )
         else echo "${D}matter-bridge skipped: cd matter-bridge && npm install${R}"; fi
         echo "${D}e2e is the slow half: cd app && npm run build && npm run e2e${R}" ;;
  help|-h|--help) usage ;;
  *)     usage; exit 1 ;;
esac

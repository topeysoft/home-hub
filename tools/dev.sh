#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# The first command to run in this checkout, whether you have never seen it or were here last month.
#
#   tools/dev.sh          where you left it — or, in a fresh clone, what this is and what to run
#   tools/dev.sh up       install whatever is missing, then the panel on a mock house
#   tools/dev.sh hub      the panel against a real brain, started fresh so it is your code
#   tools/dev.sh live     the panel against a house that is up and lived in, its brain answering
#   tools/dev.sh check    what CI runs, here, before pushing
#   tools/dev.sh design   every artboard in a browser, on the canvas they were drawn on
#   tools/dev.sh free     let go of a port something is still listening on from yesterday
#   tools/dev.sh graft    this tree's brain onto a hub, without a release
#   tools/dev.sh says     what a hub's brain is saying, with its request log taken out
#   tools/dev.sh puck     this tree's bridge firmware onto one puck, now, through the hub
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

# The ports this project puts things on. The leftovers in the status report and `free` both read
# this list, so a new one is named here once rather than in two places that drift apart.
known_ports() { cat <<'PORTS'
8300 the brain
8399 the mock brain
5173 vite
8123 home assistant
8402 the artboards
PORTS
}
what_is_on() { known_ports | awk -v p="$1" '$1 == p { $1 = ""; sub(/^ /, ""); print }'; }

# ---- letting go of a port ----------------------------------------------------------------------
# The brain from this morning is still on :8300, or a vite from a window you closed still holds
# 5173, and the thing you are trying to start says `address already in use` and names neither the
# process nor what to do about it. The cure is an lsof and a kill, and the kill is easy to aim at
# the pid above the one you meant, so it is here with the aiming already done.
#
# Two cares are borrowed from brain/dev.py, both learned the hard way. A port that a container
# publishes is held by docker's proxy rather than by the thing inside the container, so killing it
# takes docker's networking down and leaves the container running: those are named and left alone.
# And it looks more than once, because a server with a reloader on is two processes and the
# survivor can be back on the port before the next look.
free_port() {
  local port=$1 what pid cmd base age waited hard='' stopped=''
  what=$(what_is_on "$port")
  for _pass in 1 2 3; do
    pid=$(holder "$port"); [ -n "$pid" ] || break
    cmd=$(ps -ww -o command= -p "$pid" 2>/dev/null || true)
    base=${cmd%% *}; base=${base##*/}
    case "$base" in
      *docker*|*vpnkit*|qemu*)
        row ":$port" "${Y}docker holds it${R} ${D}— pid $pid only publishes a container's port; docker stop it instead${R}"
        return 0 ;;
    esac
    age=$(uptime_of "$pid")
    kill -TERM "$pid" 2>/dev/null || {
      row ":$port" "${Y}cannot stop pid $pid${R} ${D}— ${base:-it} belongs to somebody else; sudo kill $pid${R}"
      return 1; }
    waited=0                               # four seconds: a reloader has children to take with it
    while kill -0 "$pid" 2>/dev/null && [ $waited -lt 40 ]; do sleep 0.1; waited=$((waited + 1)); done
    if kill -0 "$pid" 2>/dev/null; then kill -KILL "$pid" 2>/dev/null || true; sleep 0.2
      hard=" ${D}(it ignored the polite one)${R}"; fi
    stopped="${what:-$base} ${D}pid $pid, up $age${R}$hard"
  done
  if [ -n "$(holder "$port")" ]; then
    row ":$port" "${Y}still listening${R} ${D}— something keeps putting it back; lsof -i tcp:$port${R}"
    return 1
  fi
  if [ -n "$stopped" ]; then row ":$port" "stopped $stopped"
  else row ":$port" "${D}nothing was listening${R}"; fi
}

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
  held=
  while read -r port what; do
    pid=$(holder "$port")
    if [ -n "$pid" ]; then held=1; row ":$port" "$what ${D}pid $pid, up $(uptime_of "$pid")${R}"; fi
  done < <(known_ports)
  [ -n "$held" ] && row "free" "${D}tools/dev.sh free${R} ${D}stops those — or free 8300 for one of them${R}"

  missing=()
  [ -n "$(prereqs)" ] && missing+=("$(prereqs)")
  venv_old && missing+=("a newer python for brain/.venv")
  node_stale && missing+=("app deps")
  venv_stale && missing+=("brain deps")
  if [ ${#missing[@]} -eq 0 ]; then row "ready" "everything installed and current"
  else row "ready" "${Y}$(IFS=,; echo "${missing[*]}" | sed 's/,/, /g')${R} ${D}— tools/dev.sh up does it${R}"; fi

  echo
  echo "  ${D}tools/dev.sh up${R} — the panel on the mock brain, watched, no hub needed"
  echo "  ${D}tools/dev.sh hub${R} — the same against a brain running here   ${D}tools/dev.sh check${R} — what CI runs"
  echo "  ${D}tools/dev.sh live${R} — the same against a house that is up, every tap real"
  echo "  ${D}tools/dev.sh design${R} — the artboards, before any of it is code"
}

usage() { sed -n '4,15p' "$0" | sed 's/^# \{0,1\}//'; }

case "${1:-status}" in
  status|"") if fresh; then first_time; else where_you_were; fi ;;
  # Vite prints the address it actually took, so this does not guess one. PORT=8405 moves the mock
  # if something already holds :8399.
  #
  # The mock's port is claimed first, for the reason brain/dev.py claims :8300: a mock left running
  # from an hour ago -- or started by whoever else is working in this checkout -- makes this exit
  # with `EADDRINUSE :::8399` and a node stack, which names neither the process nor what to do. And
  # the same restraint as dev.py: only one of OUR mocks is replaced, and it is said out loud whose
  # it was. Anything else on the port is reported and left alone.
  up)    ensure panel
         port=${PORT:-8399}
         pid=$(holder "$port")
         if [ -n "$pid" ]; then
           cmd=$(ps -ww -o command= -p "$pid" 2>/dev/null || true)
           case "$cmd" in
             *mock/brain.mjs*|*mock/dev.mjs*)
               row ":$port" "${D}replacing a mock brain — pid $pid, up $(uptime_of "$pid")${R}"
               free_port "$port" >/dev/null || { row ":$port" "${Y}it would not let go${R}"; exit 1; } ;;
             *)
               base=${cmd%% *}
               row ":$port" "${Y}held by ${base##*/}${R} ${D}— pid $pid, up $(uptime_of "$pid"), not a mock of ours${R}"
               echo "  ${D}tools/dev.sh free $port to stop it, or PORT=8405 tools/dev.sh up to go around it${R}" >&2
               exit 1 ;;
           esac
         fi
         cd app && exec env PORT="$port" npm run dev:mock ;;
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
  # The panel from this tree, against a house somebody lives in. No brain is started here: the
  # house's own is the one answering, which is the whole point and is also the rule -- a second brain
  # against a real house reads their Home Assistant and starts provisioning drivers.
  #
  # It hands you the stale-brain trap the other way round, though. Everywhere else in this script the
  # danger is a hub older than your code; here that is the ordinary case, because their hub follows
  # released code and you are twenty commits into a branch. A route your panel calls and their brain
  # has never heard of comes back 404 and draws as a missing feature. /alive is open to anyone and
  # carries the commit, so the gap is on the screen before Vite starts rather than in a bug report.
  live)  ensure panel
         house=${2:-hub.local}
         BRAIN="http://${house}:8300"
         alive=$(curl -fsS -m 5 "$BRAIN/alive" 2>/dev/null || true)
         if [ -z "$alive" ]; then
           echo "${Y}no brain answering at $BRAIN${R}" >&2
           echo "  ${D}tools/dev.sh live <name-or-address>  — the brain is on :8300, behind the front door on :80${R}" >&2
           exit 1
         fi
         say() { printf '%s' "$alive" | sed -n "s/.*\"$1\":\"\\([^\"]*\\)\".*/\\1/p"; }
         row "house" "$house ${D}— running $(say version)${R}"
         # `git rev-list` needs the commit to be in this checkout; a hub on code that never landed
         # here is a real answer too, and a more alarming one than being ahead of it.
         if ahead=$(git rev-list --count "$(say commit)..HEAD" 2>/dev/null); then
           [ "$ahead" != 0 ] && row "ahead" "${Y}this tree is $(n "$ahead" commit) past that brain${R} ${D}— a route it has not got answers 404${R}"
         else
           row "ahead" "${Y}its commit is not in this checkout${R} ${D}— git fetch, or that hub is on code nobody merged${R}"
         fi
         row "taps" "${Y}real${R} ${D}— their lights, their names, their Restart and Install buttons${R}"
         # A house with a code wants a phone before it will say anything, and the panel asks for one:
         # the join screen comes up here and somebody at their wall lets this laptop in. The cookie
         # that comes back is the dev server's own, so it is undone by removing that phone on Settings.
         echo
         cd app && exec env BRAIN="$BRAIN" npm run dev ;;
  # THIS TREE'S BRAIN, ON A HUB, WITHOUT A RELEASE. `live` does this for the panel; this is the
  # other half, and it exists because the round trip for one line of brain code was push to main,
  # wait for CI to build an image, wait for the hub to update. Two evenings of strip work went that
  # way before anybody said it out loud.
  #
  # It copies hub/ and vendor/ into the running container and restarts it. Nothing is installed and
  # nothing is merged: `docker compose up -d --force-recreate brain` puts the hub back on its own
  # image, and so does the next update, so a hub left like this heals itself rather than drifting
  # quietly. The container keeps reporting the version it was built from, which is why the line
  # below says so -- /alive will lie about what is running, and that is the trap to know about.
  #
  # Same warning as `live`: it is a real house. Their lights, their names, their Restart button.
  graft) house=${2:-hub.local}
         # SetEnv, because ssh otherwise forwards this Mac's locale to a hub that does not have it
         # and every remote command opens with a setlocale warning that looks like a fault.
         ssh -o BatchMode=yes -o SetEnv=LC_ALL=C -o ConnectTimeout=8 "pi@$house" true 2>/dev/null || {
           echo "${Y}cannot ssh to pi@$house${R}" >&2
           echo "  ${D}tools/dev.sh graft <name-or-address>${R}" >&2; exit 1; }
         # Compile it here first. Shipping a syntax error to a house and finding out from a
         # container that will not start is a slow way to learn you typed a colon.
         python3 -m compileall -q brain/hub >/dev/null || { echo "${Y}brain does not compile${R}" >&2; exit 1; }
         row "house" "$house"
         row "taps" "${Y}real${R} ${D}— their lights, their names, their Restart button${R}"
         # The compose file is in driver-layer, not /opt/home-hub: from anywhere else `docker compose`
         # says "no configuration file provided" and the graft quietly stays. Found undoing one.
         row "undo" "${D}ssh pi@$house 'cd /opt/home-hub/driver-layer && sudo docker compose up -d --force-recreate brain', or the next update${R}"
         # --no-xattrs, because bsdtar on a Mac writes com.apple.provenance into every header and
         # GNU tar on the hub then prints a warning per file. Nothing is wrong; it just looks it.
         COPYFILE_DISABLE=1 tar --no-xattrs -czf - -C brain hub vendor 2>/dev/null \
           | ssh -o BatchMode=yes -o SetEnv=LC_ALL=C "pi@$house" 'tmp=$(mktemp -d) && tar xzf - -C "$tmp" 2>/dev/null \
               && sudo -n docker cp "$tmp/hub" brain:/srv/brain/ \
               && sudo -n docker cp "$tmp/vendor" brain:/srv/brain/ \
               && rm -rf "$tmp" && sudo -n docker restart brain >/dev/null && echo grafted'
         row "note" "${Y}/alive still reports the image's commit${R} ${D}— it cannot see what was copied over it${R}" ;;
  # WHAT THE HUB IS SAYING, WITHOUT SSH-ING INTO IT. The brain's own lines are drowned in one
  # request log line per poll -- the panel asks every two seconds -- so `docker logs` is unreadable
  # exactly when something is going wrong. This is the filter you would have typed, and it follows.
  #
  # It cost an evening to learn that the brain logs at all: a strip refused three times and the
  # reason was in there each time, under three hundred lines of GET /strip.
  says) house=${2:-hub.local}
        row "house" "$house ${D}— its own lines only, following${R}"
        exec ssh -o BatchMode=yes -o SetEnv=LC_ALL=C "pi@$house" \
          'sudo -n docker logs -f --tail 200 brain 2>&1 | grep --line-buffered -avE "HTTP/1.1|WebSocket|connection (open|closed|rejected)"' ;;
  # A PUCK ON THIS TREE'S FIRMWARE, WITHOUT WAITING FOR THE NIGHT (brain/hub/bridge_updates.py).
  # Builds the shipped env with a development version -- BRIDGE_FW plus "-d<minutes>", which the puck
  # sorts after the last release and before BRIDGE_FW itself -- parks it in the brain's data over
  # ssh, and follows what the puck says. Only a hub on a branch channel takes it. The puck keeps every
  # rule it has: the hash, three minutes to prove itself, and back to what it had if it does not.
  #
  #   tools/dev.sh puck                     the one bridge on the broker, or a list to pick from
  #   tools/dev.sh puck list                every bridge the hub set up: room, chip, version, online
  #   tools/dev.sh puck hallway             by the room it serves...
  #   tools/dev.sh puck c0e33a              ...or by its chip
  #   tools/dev.sh puck hallway 192.168.86.53   through a hub other than hub.local
  puck)  which=${2:-}; house=${3:-hub.local}
         ssh -o BatchMode=yes -o SetEnv=LC_ALL=C -o ConnectTimeout=8 "pi@$house" true 2>/dev/null || {
           echo "${Y}cannot ssh to pi@$house${R}" >&2; exit 1; }
         SSH=(ssh -o BatchMode=yes -o SetEnv=LC_ALL=C "pi@$house")
         # Which puck, in the words the hub has for it. The brain keeps this list (bridge_updates.py,
         # list_for_tool) because the room is worked out from the house, and only the brain has that.
         known=$("${SSH[@]}" 'sudo -n docker exec brain cat /data/bridge-push/bridges.json 2>/dev/null' || true)
         [ -n "$known" ] || { echo "${Y}$house's brain keeps no list of bridges${R} ${D}— it is older than this tool; put the development brain on it first${R}" >&2; exit 1; }
         set +e
         chip=$(KNOWN="$known" WHICH="$which" python3 - <<'PY'
import json, os, sys
bs, w = json.loads(os.environ["KNOWN"]), os.environ["WHICH"].strip().lower()
def line(b):
    return f"  {(b['room'] or '(no room)'):<16} {b['chip']}  {(b['fw'] or '?'):<16} {'online' if b['online'] else 'not on the broker'}"
if w == "list" or not bs:
    print("\n".join(map(line, bs)) or "  this hub has not set up a bridge", file=sys.stderr); sys.exit(2)
hits = [b for b in bs if w in (b["chip"].lower(), (b["room"] or "").lower())] if w else [b for b in bs if b["online"]]
if len(hits) == 1: print(hits[0]["chip"]); sys.exit(0)
print(f"no bridge is {w!r}:" if w and not hits else "which one?" if hits else "none of them is on the broker:", file=sys.stderr)
print("\n".join(map(line, hits or bs)), file=sys.stderr)
print("  tools/dev.sh puck <room or chip>", file=sys.stderr); sys.exit(1)
PY
         ); rc=$?
         set -e
         [ $rc -eq 2 ] && exit 0
         [ $rc -eq 0 ] || exit 1
         command -v pio >/dev/null 2>&1 || { echo "${Y}no pio on PATH${R} ${D}— PlatformIO builds the firmware${R}" >&2; exit 1; }
         base=$(sed -n 's/^#define BRIDGE_FW "\(.*\)"/\1/p' brilliant/esp32-bridge/src/config.h)
         fw="$base-d$(( ($(date -u +%s) - 1767225600) / 60 ))"     # minutes since 2026: short, and always rising
         row "puck" "$chip ${D}via $house${R}"
         row "build" "$fw ${D}— esp32s3-ship, from this tree as it is${R}"
         ( cd brilliant/esp32-bridge && PLATFORMIO_BUILD_FLAGS="-DBRIDGE_FW=\\\"$fw\\\"" pio run -e esp32s3-ship >/dev/null ) \
           || { echo "${Y}the build failed${R} ${D}— cd brilliant/esp32-bridge && pio run -e esp32s3-ship${R}" >&2; exit 1; }
         img=brilliant/esp32-bridge/.pio/build/esp32s3-ship/firmware.bin
         grep -aq "bridge $fw ===" "$img" || { echo "${Y}the image does not carry $fw${R} ${D}— BRIDGE_FW did not take${R}" >&2; exit 1; }
         "${SSH[@]}" 'sudo -n docker exec brain sh -c "mkdir -p /data/bridge-push && rm -f /data/bridge-push/state.json"'
         "${SSH[@]}" 'sudo -n docker exec -i brain sh -c "cat > /data/bridge-push/image.bin"' < "$img"
         # The request goes last: it is what the brain looks for, so the image is whole by then.
         printf '{"chip": "%s", "fw": "%s"}' "$chip" "$fw" \
           | "${SSH[@]}" 'sudo -n docker exec -i brain sh -c "cat > /data/bridge-push/request.json"'
         row "sent" "$(wc -c < "$img" | tr -d ' ') bytes ${D}— following what the puck says${R}"
         said=""; t0=$(date +%s)
         while :; do
           now=$("${SSH[@]}" 'sudo -n docker exec brain cat /data/bridge-push/state.json 2>/dev/null' || true)
           if [ -n "$now" ] && [ "$now" != "$said" ]; then
             said=$now
             st=$(printf '%s' "$now" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["state"], d.get("why") or "")')
             row "$(date +%T)" "$st"
             case "$st" in installed*) exit 0 ;; refused*|failed*|rolledback*) exit 1 ;; esac
           fi
           [ $(( $(date +%s) - t0 )) -lt 480 ] || { row "gave up" "${Y}nothing final in eight minutes${R} ${D}— tools/dev.sh says $house${R}"; exit 1; }
           sleep 3
         done ;;
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
  # What is listening, gone. No argument means everything this project is known to put something
  # on, which is the state the status report has just described; naming ports frees only those.
  #
  #   tools/dev.sh free              8300, 8399, 5173, 8123, 8402 — whichever are held
  #   tools/dev.sh free 5173 8300    only these
  free)  shift || true
         if [ $# -eq 0 ]; then while read -r port _; do set -- "$@" "$port"; done < <(known_ports); fi
         rc=0
         for port in "$@"; do
           case "$port" in ''|*[!0-9]*)
             echo "${Y}not a port: $port${R}" >&2; echo "  ${D}tools/dev.sh free [port ...]${R}" >&2; exit 1 ;;
           esac
           free_port "$port" || rc=1
         done
         exit $rc ;;
  help|-h|--help) usage ;;
  *)     usage; exit 1 ;;
esac

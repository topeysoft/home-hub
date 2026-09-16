#!/usr/bin/env bash
# Applies an update the panel asked for, and undoes one that does not come back.
#
# home-hub-update.path starts this the moment brain-data/update.request appears. install.sh does the
# actual work (code to whichever release or commit this hub's channel points at, images pulled,
# containers restarted); update.json tells the brain, and so the panel, how it went.
#
# The undo is the reason this script is longer than the installer's call. A household's only repair
# tool is the wall, and the wall is exactly what is missing when an update does not start, so the
# hub has to put itself back rather than wait for somebody with ssh. Before anything moves, where
# the hub is now -- its commit and the image the brain container is actually running, taken from the
# daemon rather than from a file that could disagree with it -- goes into update.prev. Afterwards
# the brain has to answer on the loopback, and keep answering, or all of that is restored and the
# version that did it is named in update.json so nothing offers it again on its own.
#
# Putting it back needs no network: the old image is still in the local store. That matters, because
# a hub most likely to need the undo is a hub whose update just broke its own networking.
#
# Safe to run by hand.
set -uo pipefail
DIR="${HOME_HUB_DIR:-/opt/home-hub}"
DATA="$DIR/driver-layer/brain-data"
ENVF="$DIR/driver-layer/.env"
REQ="$DATA/update.request"; STATE="$DATA/update.json"; LOG="$DATA/update.log"; PREV="$DATA/update.prev"
# The brain is on host networking, so the host reaches it directly. /alive is open on purpose and
# carries nothing about the house: see docs/updates.md, piece 1.
ALIVE="${HOME_HUB_ALIVE:-http://127.0.0.1:8300/alive}"
WAIT="${HOME_HUB_UPDATE_WAIT:-300}"      # how long the brain has to come back at all
SETTLE="${HOME_HUB_UPDATE_SETTLE:-45}"   # ...and how long it then has to keep answering

[ -f "$REQ" ] || exit 0
# The hub's channel lives in the compose .env. Without passing it on, install.sh would fall back to
# its default and quietly move a hub that follows main onto releases.
CHANNEL="$(sed -n 's/^HUB_CHANNEL=//p' "$ENVF" 2>/dev/null | tail -1)"
CHANNEL="${CHANNEL:-release}"
# Which version the panel was looking at, so a rejected one can be named. The request stays advisory:
# it says what was wanted, never what gets installed -- that is the channel's business, and keeping
# it that way is what stops anything that can write into brain-data choosing the code that runs here.
WANT="$(sed -n 's/.*"to": *"\([^"]*\)".*/\1/p' "$REQ" | head -1)"
rm -f "$REQ"

field() { sed -n "s/.*\"$1\": *\"\([^\"]*\)\".*/\1/p" "$2" 2>/dev/null | head -1; }

running_image() {
  # What the brain container is running right now, by digest where there is one. An image built on
  # the hub itself has no digest; its id pins just as well.
  local id ref
  id="$(docker inspect --format '{{.Image}}' brain 2>/dev/null)"
  [ -n "$id" ] || return 0
  ref="$(docker image inspect --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{end}}' "$id" 2>/dev/null)"
  echo "${ref:-$id}"
}

alive() { curl -fsS --max-time 5 "$ALIVE" >/dev/null 2>&1; }

came_back() {
  # One answer is not proof: an image that starts, answers and then falls over on the data it found
  # would pass. It has to answer, and still be answering after the settle.
  local deadline
  deadline=$(( $(date +%s) + WAIT ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    alive && break
    sleep 5
  done
  alive || return 1
  sleep "$SETTLE"
  alive
}

put_back() {
  local sha img
  sha="$(field sha "$PREV")"; img="$(field image "$PREV")"
  [ -n "$sha" ] || return 1
  {
    echo "--- putting the hub back on $sha ${img:+($img)}"
    git -C "$DIR" reset -q --hard "$sha" || return 1
    git -C "$DIR" clean -qfd -e driver-layer/
    # The pin has to outlive this script: a compose run by any other hand would otherwise resolve
    # :latest and walk straight back onto the build that did not start.
    if [ -n "$img" ] && [ -f "$ENVF" ]; then
      sed -i '/^HUB_BRAIN_IMAGE=/d' "$ENVF"
      echo "HUB_BRAIN_IMAGE=$img" >> "$ENVF"
    fi
    (cd "$DIR/driver-layer" && docker compose up -d --remove-orphans)
  } >> "$LOG" 2>&1
}

STARTED="$(date +%s)"
printf '{"sha":"%s","image":"%s","at":%s}\n' \
  "$(git -C "$DIR" rev-parse HEAD 2>/dev/null)" "$(running_image)" "$STARTED" > "$PREV"
printf '{"state":"running","started":%s}\n' "$STARTED" > "$STATE"

# Nothing is undone that cannot first be checked: without curl the hub cannot tell a house that came
# back from one that did not, and guessing would turn a working update into a rollback.
PROVE=1; command -v curl >/dev/null 2>&1 || PROVE=""

finish() {  # state, extra json
  printf '{"state":"%s","started":%s,"finished":%s,"commit":"%s"%s}\n' \
    "$1" "$STARTED" "$(date +%s)" "$(git -C "$DIR" rev-parse HEAD 2>/dev/null || echo unknown)" "${2:-}" > "$STATE"
}

if HOME_HUB_DIR="$DIR" HOME_HUB_CHANNEL="$CHANNEL" "$DIR/install.sh" > "$LOG" 2>&1; then
  # What the hub has just been moved onto, for naming a version that turns out not to work. The
  # request said what was wanted; this says what arrived, which is the one to refuse next time.
  GOT="${WANT:-$(git -C "$DIR" describe --tags --exact-match 2>/dev/null || git -C "$DIR" rev-parse --short HEAD 2>/dev/null)}"
  if [ -z "$PROVE" ] || came_back; then
    finish 'done' ',"to":"'"$GOT"'"'
  else
    echo "the hub did not come back after $WAIT seconds on $GOT; putting it back" >> "$LOG"
    if put_back && { [ -z "$PROVE" ] || came_back; }; then
      finish reverted ',"bad":"'"$GOT"'","log":"update.log"'
    else
      # Put back and still not answering. Say so plainly rather than claim a rollback that did not
      # take: this is the one case where somebody has to be told to get in touch.
      finish failed ',"bad":"'"$GOT"'","reverted":false,"log":"update.log"'
    fi
    exit 1
  fi
else
  # The installer stopped part way, which can leave the checkout moved and the containers not. Put
  # the hub back on what it was before rather than leave it between two versions.
  put_back
  finish failed ',"log":"update.log"'
  exit 1
fi

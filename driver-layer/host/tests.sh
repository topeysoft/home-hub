#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# The update path, exercised rather than read.
#
# Everything under host/ is the safety net for a hub in somebody's house: the undo that puts a build
# back when it does not start, the signature that decides what may run as root, and the hold that
# stops a bad release spreading. Until this existed CI checked their syntax and nothing more, which
# is the weakest possible guarantee about the three scripts a household most depends on and can
# least repair. docs/updates.md.
#
# It needs git, openssl, curl and python3 and nothing else -- no docker, no network, no root. The
# registry and the releases server are a directory and a `file://` URL; the only Docker in here is a
# shell script on PATH that prints what the daemon would have said.
#
#   driver-layer/host/tests.sh            all of it
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PASS=0; FAIL=0

ok() { PASS=$((PASS + 1)); printf '  \033[32m✓\033[0m %s\n' "$1"; }
no() { FAIL=$((FAIL + 1)); printf '  \033[31m✗\033[0m %s — %s\n' "$1" "$2"; }
is() { [ "$2" = "$3" ] && ok "$1" || no "$1" "wanted $3, got $2"; }
group() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# A hub: a checkout with two releases on it, sitting on the older one.
hub() {
  local dir="$1"
  mkdir -p "$dir/driver-layer/brain-data" "$dir/driver-layer/host"
  cp "$HERE/verify.sh" "$dir/driver-layer/host/"          # the hub has its own copy; channel.sh reads it
  git init -q "$dir"; git -C "$dir" config user.email t@t; git -C "$dir" config user.name t
  echo old > "$dir/f"; git -C "$dir" add -A; git -C "$dir" commit -qm old; git -C "$dir" tag v0.2.0
  echo new > "$dir/f"; git -C "$dir" add -A; git -C "$dir" commit -qm new; git -C "$dir" tag v0.3.0
  git -C "$dir" reset -q --hard v0.2.0
}

keypair() { openssl genpkey -algorithm ed25519 -out "$1" 2>/dev/null; openssl pkey -in "$1" -pubout -out "$2" 2>/dev/null; }
sign() { openssl pkeyutl -sign -inkey "$2" -rawin -in "$1" -out "$1.sig"; }

manifest() {  # file, version, commit, min_from
  cat > "$1" <<J
{
  "schema": 1,
  "version": "$2",
  "commit": "$3",
  "brain": "ghcr.io/topeysoft/home-hub-brain@sha256:aaaa",
  "images": {
    "caddy": "caddy@sha256:bbbb",
    "mosquitto": "eclipse-mosquitto@sha256:cccc"
  },
  "min_from": "${4:-v0.1.0}"
}
J
}

channel_file() {  # file, held version (or empty), made
  cat > "$1" <<J
{
  "schema": 1,
  "made": "${3:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}",
  "hold": [
    "${2:-v9.9.9}"
  ],
  "rollout": {}
}
J
}

# Run verify_release in a subshell so the sourced functions and exports never leak between cases.
verify() {  # keys dir, releases dir, hub dir -> prints rc
  ( HOME_HUB_KEYS="$1" HOME_HUB_RELEASES="file://$2" . "$HERE/verify.sh" >/dev/null 2>&1
    verify_release v0.3.0 "$3" >/dev/null 2>&1; echo $? )
}


# ---------------------------------------------------------------- what may run as root in a house
signatures() {
  group "A release is what the maker signed, or it is not installed"
  local root; root="$(mktemp -d)"
  local dir="$root/hub" serve="$root/serve" keys="$root/keys"
  mkdir -p "$serve/v0.3.0" "$keys"; hub "$dir"
  local commit; commit="$(git -C "$dir" rev-list -n 1 v0.3.0)"
  local old; old="$(git -C "$dir" rev-list -n 1 v0.2.0)"
  keypair "$root/maker.pem" "$keys/release.pub"
  keypair "$root/thief.pem" "$root/thief.pub"
  local m="$serve/v0.3.0/release.json"

  manifest "$m" v0.3.0 "$commit"; sign "$m" "$root/maker.pem"
  is "signed by the maker, tag and commit agree: installs" "$(verify "$keys" "$serve" "$dir")" 0

  manifest "$m" v0.3.0 "$old"; sign "$m" "$root/maker.pem"
  is "the tag was moved onto another commit: refuses" "$(verify "$keys" "$serve" "$dir")" 1

  manifest "$m" v0.3.0 "$commit"; sign "$m" "$root/thief.pem"
  is "signed by a key this hub does not hold: refuses" "$(verify "$keys" "$serve" "$dir")" 1

  manifest "$m" v0.3.0 "$commit"; sign "$m" "$root/maker.pem"
  manifest "$m" v0.3.0 "$old"                                  # edited after signing
  is "the record was changed after signing: refuses" "$(verify "$keys" "$serve" "$dir")" 1

  manifest "$m" v0.3.0 "$commit"; sign "$m" "$root/maker.pem"; rm -f "$m.sig"
  is "no signature published at all: refuses" "$(verify "$keys" "$serve" "$dir")" 1

  manifest "$m" v9.9.9 "$commit"; sign "$m" "$root/maker.pem"
  is "the record names a different version: refuses" "$(verify "$keys" "$serve" "$dir")" 1

  manifest "$m" v0.3.0 "$commit" v0.2.5; sign "$m" "$root/maker.pem"
  is "an upgrade path below min_from: refuses" "$(verify "$keys" "$serve" "$dir")" 1

  manifest "$m" v0.3.0 "$commit"; sign "$m" "$root/maker.pem"
  is "a hub with no keys yet says so rather than pretending" "$(verify "$root/no-keys-here" "$serve" "$dir")" 2

  # What a good verification leaves the caller holding, under the names docker-compose.yml reads: a
  # spelling mistake here is silent, and every image quietly comes down by tag instead of by digest.
  local got
  got="$( HOME_HUB_KEYS="$keys" HOME_HUB_RELEASES="file://$serve" . "$HERE/verify.sh" >/dev/null 2>&1
          verify_release v0.3.0 "$dir" >/dev/null 2>&1
          echo "$VERIFIED_COMMIT ${HUB_BRAIN_IMAGE##*@} $(echo "$HUB_IMAGE_VARS" | xargs)" )"
  is "the caller is left the commit to check out" "${got%% *}" "$commit"
  case "$got" in
    *"sha256:aaaa HUB_IMG_CADDY HUB_IMG_MOSQUITTO"*) ok "...the brain digest and one HUB_IMG_ per service" ;;
    *) no "...the brain digest and one HUB_IMG_ per service" "got: $got" ;;
  esac

  # install.sh calls this from inside go_to_ref, under set -u. A cleanup trap that outlived the check
  # fired again when go_to_ref returned, found its variable gone, and stopped every verified install
  # after the checkout had already moved -- so update.sh put it back, and the house never updated.
  got="$( bash -c 'set -euo pipefail
                   HOME_HUB_KEYS="$1" HOME_HUB_RELEASES="file://$2" . "$4/verify.sh" >/dev/null 2>&1
                   hub="$3"; go() { verify_release v0.3.0 "$hub" >/dev/null 2>&1; }
                   go; echo carried-on' _ "$keys" "$serve" "$dir" "$HERE" 2>&1 )"
  is "the installer carries on past a verified release" "$got" carried-on
  rm -rf "$root"
}


# ------------------------------------------------------- and what the maker is saying about it now
holds() {
  group "A release the maker has pulled since signing it"
  local root; root="$(mktemp -d)"
  local dir="$root/hub" serve="$root/serve" keys="$root/keys"
  mkdir -p "$serve/v0.3.0" "$serve/channel" "$keys"; hub "$dir"
  local commit; commit="$(git -C "$dir" rev-list -n 1 v0.3.0)"
  keypair "$root/maker.pem" "$keys/release.pub"
  keypair "$root/thief.pem" "$root/thief.pub"
  manifest "$serve/v0.3.0/release.json" v0.3.0 "$commit"; sign "$serve/v0.3.0/release.json" "$root/maker.pem"

  local fetch='HOME_HUB_DIR="'"$dir"'" HOME_HUB_KEYS="'"$keys"'" HOME_HUB_RELEASES="file://'"$serve"'"'
  ask() { eval "$fetch" "$HERE/channel.sh" >/dev/null 2>&1; }
  local c="$serve/channel/channel.json"

  channel_file "$c" v9.9.9; sign "$c" "$root/maker.pem"; ask
  is "nothing held: installs" "$(verify "$keys" "$serve" "$dir")" 0

  channel_file "$c" v0.3.0; sign "$c" "$root/maker.pem"; ask
  is "held by the maker: refuses" "$(verify "$keys" "$serve" "$dir")" 1

  channel_file "$c" v0.3.0; sign "$c" "$root/thief.pem"; ask
  is "a hold signed by somebody else withholds nothing" "$(verify "$keys" "$serve" "$dir")" 0
  [ -f "$dir/driver-layer/brain-data/channel.json" ] \
    && no "...and is not written to disk" "it was written" || ok "...and is not written to disk"

  channel_file "$c" v0.3.0 2020-09-16T00:00:00Z; sign "$c" "$root/maker.pem"; ask
  is "a genuine hold replayed from years ago is ignored" "$(verify "$keys" "$serve" "$dir")" 0

  rm -f "$c" "$c.sig"; ask
  is "a maker who publishes nothing holds nothing" "$(verify "$keys" "$serve" "$dir")" 0

  # The one that caught a harness lying about all of the above: without verify.sh there is no way to
  # check a channel file, and a hub that cannot check one must not be told by one.
  channel_file "$c" v0.3.0; sign "$c" "$root/maker.pem"; ask
  rm -f "$dir/driver-layer/host/verify.sh"; ask
  [ -f "$dir/driver-layer/brain-data/channel.json" ] \
    && no "a hub that cannot check a hold drops the one it had" "it kept it" \
    || ok "a hub that cannot check a hold drops the one it had"
  rm -rf "$root"
}


# ------------------------------------------------------------------- and the undo, which is piece 1
undo() {
  group "An update that does not come back is put back"
  local root; root="$(mktemp -d)"
  local dir="$root/hub" bin="$root/bin" fake="$root/fake" data
  data="$dir/driver-layer/brain-data"
  mkdir -p "$bin" "$fake"; hub "$dir"
  local old new; old="$(git -C "$dir" rev-list -n 1 v0.2.0)"; new="$(git -C "$dir" rev-list -n 1 v0.3.0)"

  cat > "$bin/docker" <<'D'
#!/usr/bin/env bash
case "$1 ${2:-}" in
  "inspect --format") echo "sha256:oldimageid" ;;
  "image inspect")    echo "ghcr.io/topeysoft/home-hub-brain@sha256:olddigest" ;;
  "compose up")       touch "$FAKE/answering" ;;   # the old brain is back and answering
esac
D
  cat > "$bin/curl" <<'C'
#!/usr/bin/env bash
[ -f "$FAKE/answering" ]
C
  cat > "$bin/systemctl" <<'S'
#!/usr/bin/env bash
exit 0
S
  chmod +x "$bin/docker" "$bin/curl" "$bin/systemctl"

  start() {  # $1 = whether the installer succeeds, $2 = whether the new build answers
    git -C "$dir" reset -q --hard "$old"
    printf 'HUB_CHANNEL=release\nTZ=UTC\n' > "$dir/driver-layer/.env"
    cat > "$dir/install.sh" <<I
#!/usr/bin/env bash
git -C "$dir" reset -q --hard "$new"
printf '{"phase":"restarting","at":%s}\\n' "\$(date +%s)" >> "\$HUB_PROGRESS"
[ "$1" = ok ] && { [ "$2" = ok ] && touch "\$FAKE/answering"; exit 0; }
exit 1
I
    chmod +x "$dir/install.sh"
    rm -f "$fake/answering"
    printf '{"at":1,"channel":"release","from":"v0.2.0","to":"v0.3.0"}' > "$data/update.request"
  }
  run() { PATH="$bin:$PATH" FAKE="$fake" HOME_HUB_DIR="$dir" HOME_HUB_UPDATE_WAIT=4 HOME_HUB_UPDATE_SETTLE=1 \
          "$HERE/update.sh" >/dev/null 2>&1; }
  state() { sed -n 's/.*"state":"\([a-z]*\)".*/\1/p' "$data/update.json"; }
  # The phases, in the order they were written. This is the panel's only clock and the only place the
  # dark stretch is measurable, so what is checked here is that the two scripts write to the SAME file
  # -- update.sh's own phases and the ones install.sh adds from inside its run.
  phases() { sed -n 's/.*"phase": *"\([a-z_]*\)".*/\1/p' "$data/update.progress" 2>/dev/null | tr '\n' ' ' | sed 's/ $//'; }
  at() { git -C "$dir" rev-parse HEAD; }

  start ok ok
  printf '{"phase":"proving","at":1}\n' > "$data/update.progress"   # last time's, and not this time's
  run
  is "it installed and came back: done" "$(state)" 'done'
  is "...and the hub is on the new build" "$(at)" "$new"
  is "...and left a timeline, the installer's phases in it too" "$(phases)" 'checking restarting proving'

  start ok no; run
  is "it installed and did not come back: reverted" "$(state)" reverted
  # The six minutes this piece exists for. A panel cannot hear this phase -- the brain is not there to
  # be asked -- but the hub that comes back can, which is how "that one did not start" gets said at all.
  is "...and the putting back is on the record" "$(phases)" 'checking restarting putting_back proving'
  is "...and the hub is back where it was" "$(at)" "$old"
  case "$(cat "$dir/driver-layer/.env")" in
    *"HUB_BRAIN_IMAGE=ghcr.io/topeysoft/home-hub-brain@sha256:olddigest"*)
      ok "...with the old image pinned, so nothing walks back onto the new one" ;;
    *) no "...with the old image pinned" "no pin in .env" ;;
  esac

  start fail no; run
  is "the installer stopped part way: put back" "$(at)" "$old"
  is "...and says so" "$(state)" failed

  start ok ok; run >/dev/null
  [ -f "$data/update.request" ] && no "the request never survives a run" "it is still there" \
                                || ok "the request never survives a run, so a hub cannot loop"
  rm -rf "$root"
}


# What a stick is taken for. One substring in one pattern decided that an ESP32 bridge puck was a
# Z-Wave controller -- zwave-js-ui held its port open for as long as it was plugged in, and the hub
# could never talk to its own puck. The matching is pure and radios.sh can be asked about one name
# without touching anything, so there is no reason for it not to be held here.
radios() {
  group "which radio is which"
  local r="$HERE/../radios.sh"
  taken() { "$r" which "$1"; }

  is "an ESP32 bridge puck is not a radio, whatever its serial number reads" \
     "$(taken usb-1a86_USB_Single_Serial_5A46080020-if00)" none
  is "...and neither is one on its native USB port" \
     "$(taken usb-Espressif_USB_JTAG_serial_debug_unit_34:85:18:AB-if00)" none
  # The pattern the puck collided with. It is there for a real stick and has to keep finding it.
  is "an 800-series Z-Wave stick still is one" \
     "$(taken usb-ZOOZ_800_Z-Wave_Stick_533D004242-if00)" zwave
  # Two radios on one plug: -if00 is the Z-Wave side and -if01 an EM3581 Zigbee2MQTT cannot drive.
  is "the HubZ is Z-Wave on -if00" \
     "$(taken usb-Silicon_Labs_HubZ_Smart_Home_Controller_C1301AAC-if00-port0)" zwave
  is "...and nothing on -if01, rather than Zigbee it cannot use" \
     "$(taken usb-Silicon_Labs_HubZ_Smart_Home_Controller_C1301AAC-if01-port0)" none
  is "a SkyConnect is Zigbee" "$(taken usb-Nabu_Casa_SkyConnect_v1.0_9e2a4f-if00)" zigbee
  is "a Sonoff dongle is Zigbee" "$(taken usb-ITead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_abc123-if00)" zigbee
  # A product that simply ends in a word must keep it, or the stripping eats the name.
  is "a stick with no serial in its name is still read by its product" \
     "$(taken usb-dresden_elektronik_ingenieurtechnik_GmbH_ConBee_II-if00)" none
}


# ------------------------------------------------------- a part left stopped after the plug was pulled
# The broker came back from a power cut marked exited and nothing started it; the brain kept answering,
# so the watchdog, which only asked the brain, saw a healthy house while every puck was locked out.
watchdog() {
  group "A part that did not come back after a power cut is started"
  local root; root="$(mktemp -d)"
  local dir="$root/hub" bin="$root/bin" fake="$root/fake" data
  data="$dir/driver-layer/brain-data"
  mkdir -p "$bin" "$fake" "$data"

  # $FAKE/states is what `compose ps -a` would print; `compose up` is written down, not done.
  cat > "$bin/docker" <<'D'
#!/usr/bin/env bash
[ -f "$FAKE/no-daemon" ] && exit 1
case "$1 ${2:-} ${3:-}" in
  "compose config --services") printf 'mosquitto\nhomeassistant\nbrain\n' ;;
  "compose ps -a")             [ "${4:-}" = -q ] && echo "id-$5" || cat "$FAKE/states" ;;
  "inspect -f {{.State.FinishedAt}}") echo "2026-09-26T22:29:45.477055085Z" ;;
  "compose up -d")             shift 3; echo "$*" >> "$FAKE/up" ;;
esac
D
  cat > "$bin/curl" <<'C'
#!/usr/bin/env bash
[ -f "$FAKE/answering" ]
C
  chmod +x "$bin/docker" "$bin/curl"

  run() {  # states, one "service state" per line
    printf '%b' "$1" > "$fake/states"; rm -f "$fake/up" "$data/restart.json" "$data/healed.jsonl"
    PATH="$bin:$PATH" FAKE="$fake" HOME_HUB_DIR="$dir" HOME_HUB_WATCHDOG_GAP=0 "$HERE/watchdog.sh" >/dev/null 2>&1
  }
  up() { cat "$fake/up" 2>/dev/null || echo nothing; }
  touch "$fake/answering"

  run 'mosquitto exited\nhomeassistant running\nbrain running\n'
  is "the broker left exited is started, and only it" "$(up)" mosquitto
  [ -f "$data/restart.json" ] && no "...without telling the brain it restarted" "restart.json was written" \
                              || ok "...without telling the brain it restarted, because it did not"
  # What the brain reads to say so on What happened: the part, and when Docker says it stopped.
  python3 -c 'import json,sys; r=json.loads(open(sys.argv[1]).read()); print(r["parts"][0]["service"], r["parts"][0]["stopped"][:19], "at" in r)' \
    "$data/healed.jsonl" > "$fake/said" 2>&1
  is "...and writes down what it started, and when that stopped" "$(cat "$fake/said")" "mosquitto 2026-09-26T22:29:45 True"

  run 'homeassistant running\nbrain running\n'
  is "a part that was never created is started" "$(up)" mosquitto

  run 'mosquitto restarting\nhomeassistant running\nbrain running\n'
  is "a part compose is already restarting is left to compose" "$(up)" nothing

  run 'mosquitto running\nhomeassistant running\nbrain running\n'
  is "a whole house is left alone" "$(up)" nothing
  [ -f "$data/healed.jsonl" ] && no "...and writes nothing down" "healed.jsonl was written" || ok "...and writes nothing down"

  touch "$data/update.request"
  run 'mosquitto exited\nhomeassistant running\nbrain running\n'
  is "an update in flight is not raced" "$(up)" nothing
  rm -f "$data/update.request"

  touch "$fake/no-daemon"
  run 'mosquitto exited\n'
  is "a docker that does not answer starts nothing" "$(up)" nothing
  rm -rf "$root"
}

# ------------------------------------------------------------ outside, turned on and off from the panel
# The values arrive from a service on the internet by way of the brain and land in a file docker compose
# reads as root, so the one property worth proving is that nothing that does not look like a house's
# value ever gets in -- and that the line everybody shares, COMPOSE_PROFILES, keeps the radios'.
away() {
  group "Outside, on and off, and nothing odd reaches .env"
  local root; root="$(mktemp -d)"
  local dir="$root/hub" bin="$root/bin" fake="$root/fake" data dl
  dl="$dir/driver-layer"; data="$dl/brain-data"
  mkdir -p "$bin" "$fake" "$data"
  cat > "$bin/docker" <<'D'
#!/usr/bin/env bash
echo "$*" >> "$FAKE/docker"
D
  # What `ip route get` says this host's address on the LAN is; $FAKE/lan changes it.
  cat > "$bin/ip" <<'I'
#!/usr/bin/env bash
echo "1.1.1.1 via 192.168.86.1 dev eth0 src $(cat "$FAKE/lan" 2>/dev/null || echo 192.168.86.53) uid 0"
I
  chmod +x "$bin/docker" "$bin/ip"
  local secret token; secret="$(printf 's%.0s' $(seq 43))"; token="$(printf 'a%.0s' $(seq 64))"
  good() { printf 'HUB_AWAY_HOUSE=jordan\nHUB_RELAY_SECRET=%s\nHUB_RELAY_TOKEN=%s\nHUB_RELAY_ADDR=relay.elyir.app\nHUB_AWAY_ZONE=elyir.app\n' "$secret" "$token" > "$data/away.env"; }
  run() { printf '{"at": 1, "want": "%s"}' "$1" > "$data/away.request"; rm -f "$fake/docker"
          PATH="$bin:$PATH" FAKE="$fake" HOME_HUB_DIR="$dir" "$HERE/away.sh" >/dev/null 2>&1; }
  env_() { grep -m1 "^$1=" "$dl/.env" | cut -d= -f2-; }

  printf 'TZ=UTC\nCOMPOSE_PROFILES=zigbee,voice\n' > "$dl/.env"
  good; run on
  is "on writes the house's name" "$(env_ HUB_AWAY_HOUSE)" jordan
  is "...and its secret" "$(env_ HUB_RELAY_SECRET)" "$secret"
  is "...and turns the away door on" "$(env_ HUB_AWAY)" on
  is "...adding away beside the radios and the voice" "$(env_ COMPOSE_PROFILES)" "zigbee,voice,away"
  is "...and brings caddy, frpc and lan-cert up" "$(cat "$fake/docker")" "compose up -d caddy frpc lan-cert"
  is "...naming the house at home from the address it really has" "$(env_ HUB_LAN_NAME)" "192-168-86-53.jordan.home.elyir.app"
  [ -f "$data/away.request" ] && no "...and takes the request away" "it is still there" || ok "...and takes the request away"
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["on"], d["house"])' "$data/away.json" > "$fake/said" 2>&1
  is "...and says what it did" "$(cat "$fake/said")" "True jordan"

  run on
  is "on twice is still one away" "$(env_ COMPOSE_PROFILES)" "zigbee,voice,away"

  run off
  is "off turns the door off" "$(env_ HUB_AWAY)" off
  is "...takes away out and leaves the rest" "$(env_ COMPOSE_PROFILES)" "zigbee,voice"
  is "...keeps the name for when it comes back" "$(env_ HUB_AWAY_HOUSE)" jordan
  is "...and stops frpc and lan-cert" "$(head -1 "$fake/docker")" "compose --profile away rm -sf frpc lan-cert"

  good; run on; : > "$data/away.env"; run forget
  is "forget takes the secret out of .env" "$(grep -c '^HUB_RELAY_SECRET=' "$dl/.env")" 0
  is "...and the name" "$(grep -c '^HUB_AWAY_HOUSE=' "$dl/.env")" 0
  is "...and the name at home" "$(grep -c '^HUB_LAN_NAME=' "$dl/.env")" 0

  printf 'TZ=UTC\n' > "$dl/.env"; echo 203.0.113.9 > "$fake/lan"; good; run on
  is "a public address gets no name at home" "$(grep -c '^HUB_LAN_NAME=' "$dl/.env")" 0
  is "...and outside still comes on" "$(env_ HUB_AWAY)" on
  rm -f "$fake/lan"

  printf 'COMPOSE_PROFILES=away\n' > "$dl/.env"; good; run off
  is "the last profile going leaves none rather than nothing" "$(env_ COMPOSE_PROFILES)" none

  local before
  for bad in 'HUB_AWAY_HOUSE=jordan|evil' 'HUB_AWAY_HOUSE=Jordan' 'HUB_AWAY_HOUSE=-jordan' "HUB_RELAY_SECRET=x" 'HUB_RELAY_SECRET=abc$(reboot)defghijklmnop' \
             'HUB_RELAY_ADDR=relay.elyir.app;rm' 'HUB_AWAY_ZONE=elyir.app;HUB_IMG_BRAIN=evil/brain'; do
    printf 'TZ=UTC\nCOMPOSE_PROFILES=none\n' > "$dl/.env"; before="$(cat "$dl/.env")"
    good; key="${bad%%=*}"; grep -v "^$key=" "$data/away.env" > "$fake/v"; printf '%b\n' "$bad" >> "$fake/v"; mv "$fake/v" "$data/away.env"
    run on
    [ "$(cat "$dl/.env")" = "$before" ] && [ ! -f "$fake/docker" ] && ok "refused, .env untouched: $bad" || no "refused, .env untouched: $bad" "$(cat "$dl/.env")"
  done

  # A line away.sh does not ask for is never read: only its five keys are, each by its own pattern.
  printf 'TZ=UTC\n' > "$dl/.env"; good; printf 'HUB_IMG_BRAIN=evil/brain\n' >> "$data/away.env"; run on
  is "a key it does not ask for never reaches .env" "$(grep -c '^HUB_IMG_BRAIN=' "$dl/.env")" 0

  printf 'TZ=UTC\n' > "$dl/.env"; before="$(cat "$dl/.env")"
  run 'sideways'
  is "a want it does not know does nothing" "$(cat "$dl/.env")" "$before"
  printf '{"at": 1, "want": "on; reboot"}' > "$data/away.request"; good; rm -f "$fake/docker"
  PATH="$bin:$PATH" FAKE="$fake" HOME_HUB_DIR="$dir" "$HERE/away.sh" >/dev/null 2>&1
  is "a want with anything after it is not a want" "$(cat "$dl/.env")" "$before"
  rm -rf "$root"
}


# A unit with a screen asks this before it installs a hub of its own (design/companion/, C). The
# network is a script on PATH: avahi-browse says who announced themselves, curl says who answers like
# a hub, and hostname says which addresses are this unit's own.
finding() {
  group "a screen looks for the house's hub before it builds a second house"
  local root bin; root=$(mktemp -d); bin="$root/bin"; mkdir -p "$bin"
  cat > "$bin/avahi-browse" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$ANNOUNCED"
SH
  # A hub's front door answers only the names it was installed with (driver-layer/caddy/Caddyfile):
  # HUBS is the list of them; anything else gets Caddy's empty page.
  cat > "$bin/curl" <<'SH'
#!/usr/bin/env bash
for a in "$@"; do case "$a" in http://*) url=$a ;; esac; done
case " $HUBS " in *" ${url%/phones/me} "*) echo '{"locked": true, "paired": false, "home": "Maple Court"}' ;; *) exit 0 ;; esac
SH
  printf '#!/usr/bin/env bash\n[ "$1" = -I ] && echo "$MINE" || echo "$NAME"\n' > "$bin/hostname"
  chmod +x "$bin"/*
  find_hub() { PATH="$bin:$PATH" FIND_FOR=0 NAME="${NAME:-screen}" "$HERE/../../startup/find-hub.sh"; }

  local hub='=;eth0;IPv4;hub;_home-hub._tcp;local;hub.local;192.168.1.20;80;"path=/"'
  is "a hub that answers is found, by its name" "$(ANNOUNCED="$hub" HUBS="http://hub.local http://192.168.1.20" MINE="192.168.1.30" find_hub)" "http://hub.local"
  is "...asked by its name, because its front door has forgotten the address the router gave it since" \
    "$(ANNOUNCED="$hub" HUBS="http://hub.local" MINE="192.168.1.30" find_hub)" "http://hub.local"
  ANNOUNCED="" HUBS="" MINE="192.168.1.30" find_hub >/dev/null; is "no hub, and it says so" "$?" "1"
  ANNOUNCED="$hub" HUBS="" MINE="192.168.1.30" find_hub >/dev/null; is "something announcing itself that does not answer like a hub is not one" "$?" "1"
  is "its own announcement is not another hub" "$(ANNOUNCED="$hub" HUBS="http://hub.local" MINE="192.168.1.20" find_hub)" ""
  local self='=;lo;IPv4;hub-2;_home-hub._tcp;local;hub-2.local;127.0.0.1;80;"path=/"'
  is "...nor is its own name, on loopback" "$(ANNOUNCED="$self" HUBS="http://hub-2.local" MINE="192.168.1.30" NAME=hub-2 find_hub)" ""
  # A unit installed as a hub once is still called hub, and avahi calls it hub-2: the real hub.local is not it.
  is "a unit that was once called hub still finds the real one" "$(ANNOUNCED="$hub" HUBS="http://hub.local" MINE="192.168.1.30" NAME=hub find_hub)" "http://hub.local"
  local odd='=;eth0;IPv4;hub;_home-hub._tcp;local;hub.local;192.168.1.20;8300;"path=/"'
  is "a hub on another port keeps its port" "$(ANNOUNCED="$odd" HUBS="http://hub.local:8300" MINE="" find_hub)" "http://hub.local:8300"
  local bare='=;eth0;IPv4;hub;_home-hub._tcp;local;;192.168.1.20;80;"path=/"'
  is "an announcement with no name is asked by its address" "$(ANNOUNCED="$bare" HUBS="http://192.168.1.20" MINE="" find_hub)" "http://192.168.1.20"
  rm -rf "$root"
}


# What first boot makes of a unit: the house's screen, or the house's hub. Never a second hub beside a
# real one when the unit was told it is a screen (design/companion/, C). The checkout is fake: its
# installers leave a file saying they ran, and find-hub.sh answers with $FOUND or nothing.
becoming() {
  group "first boot makes a screen, or a hub, and never a second hub when told it is a screen"
  local root dir bin drm; root=$(mktemp -d); dir="$root/opt"; bin="$root/bin"; drm="$root/drm"
  mkdir -p "$dir/startup" "$bin" "$drm"
  printf '#!/usr/bin/env bash\n[ -n "${FOUND:-}" ] && echo "$FOUND"\n' > "$dir/startup/find-hub.sh"
  printf '#!/usr/bin/env bash\ntouch "%s/screen-installed"\n' "$root" > "$dir/startup/install.sh"
  printf '#!/usr/bin/env bash\ntouch "%s/hub-installed"\n' "$root" > "$dir/install.sh"
  for c in hostnamectl apt-get avahi-browse; do printf '#!/usr/bin/env bash\nexit 0\n' > "$bin/$c"; done
  # systemctl and docker write down what they were asked, so a unit that was a hub can be seen to stop being one
  printf '#!/usr/bin/env bash\necho "systemctl $*" >> "%s/asked"\n[ "$1" = list-unit-files ] && printf "home-hub-watchdog.timer enabled enabled\\nhome-hub-update.path enabled enabled\\n"\nexit 0\n' "$root" > "$bin/systemctl"
  printf '#!/usr/bin/env bash\necho "docker $* in $PWD" >> "%s/asked"\n' "$root" > "$bin/docker"
  mkdir -p "$dir/driver-layer" "$root/avahi"; touch "$dir/driver-layer/docker-compose.yml"
  chmod +x "$dir/startup/"*.sh "$dir/install.sh" "$bin"/*
  boot() {   # role, found, dsi
    rm -f "$root"/*-installed "$root/done" "$root/conf" "$root/asked"; rm -rf "${drm:?}"/*
    echo '<service-group/>' > "$root/avahi/home-hub.service"
    [ -n "$1" ] && echo "HUB_ROLE=\"$1\"" > "$root/conf"
    [ -n "$3" ] && { mkdir -p "$drm/card1-DSI-1"; echo connected > "$drm/card1-DSI-1/status"; }
    PATH="$bin:$PATH" FOUND="$2" HOME_HUB_DIR="$dir" HUB_CONF="$root/conf" HUB_FIRSTBOOT_MARK="$root/done" HUB_DRM="$drm" HUB_AVAHI="$root/avahi" \
      "$HERE/firstboot.sh" >/dev/null 2>&1
  }
  ran() { local out=""; for k in hub screen; do [ -f "$root/$k-installed" ] && out="$out$k "; done; [ -f "$root/done" ] && out="${out}done"; echo "${out% }"; }

  boot screen http://hub.local ""
  is "told it is a screen, on HDMI, with a hub on the Wi-Fi: it becomes the screen and nothing else" "$(ran)" "screen done"
  is "...and opens the hub's panel as a screen" "$(grep '^ELYIR_PANEL_URL=' "$root/conf")" 'ELYIR_PANEL_URL="http://hub.local/?screen=1"'
  is "...a hub it used to be stops: its timers and watchers are switched off" "$(grep -c 'systemctl disable --now home-hub-watchdog.timer home-hub-update.path' "$root/asked")" "1"
  is "...its house is taken down" "$(grep -c "docker compose down in $dir/driver-layer" "$root/asked")" "1"
  is "...and it no longer says it is a hub" "$([ -f "$root/avahi/home-hub.service" ] && echo still || echo gone)" "gone"
  is "...said once, not appended twice" "$(grep -c '^HUB_ROLE=' "$root/conf")" "1"
  boot screen "" ""; local code=$?
  is "told it is a screen, and no hub found: no hub installed, and it tries again next start" "$(ran)" ""
  is "...and says it did not finish" "$code" "1"
  boot "" http://hub.local dsi
  is "the wall's own screen and a hub on the Wi-Fi: the screen, without being told" "$(ran)" "screen done"
  boot "" "" dsi
  is "the wall's own screen and no hub: it runs the house, on its own screen" "$(ran)" "hub screen done"
  boot "" http://hub.local ""
  is "a monitor on HDMI and nobody said screen: a hub, as before, whatever is on the Wi-Fi" "$(ran)" "hub done"
  is "...and a hub keeps its house: nothing taken down" "$(cat "$root/asked" 2>/dev/null | grep -c 'compose down\|disable')" "0"
  boot hub http://hub.local dsi
  is "HUB_ROLE=hub skips the look" "$(ran)" "hub screen done"
  rm -rf "$root"
}


for need in git openssl curl python3; do
  command -v "$need" >/dev/null 2>&1 || { echo "these tests need $need"; exit 2; }
done
signatures; holds; undo; radios; watchdog; away; finding; becoming
printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

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


for need in git openssl curl python3; do
  command -v "$need" >/dev/null 2>&1 || { echo "these tests need $need"; exit 2; }
done
signatures; holds; undo; radios
printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

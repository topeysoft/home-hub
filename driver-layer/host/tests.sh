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
  at() { git -C "$dir" rev-parse HEAD; }

  start ok ok; run
  is "it installed and came back: done" "$(state)" 'done'
  is "...and the hub is on the new build" "$(at)" "$new"

  start ok no; run
  is "it installed and did not come back: reverted" "$(state)" reverted
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


for need in git openssl curl python3; do
  command -v "$need" >/dev/null 2>&1 || { echo "these tests need $need"; exit 2; }
done
signatures; holds; undo
printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

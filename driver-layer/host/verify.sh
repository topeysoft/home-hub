#!/usr/bin/env bash
# Whether a release is what the maker says it is. Sourced by install.sh; defines verify_release.
#
# The problem this exists for: install.sh used to move the checkout to whatever the newest v* tag
# pointed at and pull images by tag. Both are names somebody can move, so the answer to "what may run
# as root in this house" was "whoever can push to GitHub" -- a stolen token, a compromised Action, or
# a bad afternoon at the registry. Nothing was checked anywhere.
#
# So a release carries a small signed record of what it is (tools/release-manifest.py): the commit,
# and every image by digest. This checks the signature against a key on the host, and then the hub
# checks out the *commit the manifest names* and pulls the *digests the manifest names*. A tag that
# moves after that changes nothing, because nothing reads a tag any more.
#
# Where the key lives is the whole point. NOT in $DIR -- that is the thing being updated, so a key
# kept there could be replaced by the same push the key exists to catch. It is copied once to
# /etc/home-hub/release-key.pub, on the first install, and never overwritten afterwards. The first
# install trusts the repository it is being installed from; every update after it trusts the key.
# That boundary is real and worth knowing: a flashed image narrows it, because the image was built
# from a tag and carries the key already.
#
# Two things this deliberately does not do. It does not verify the `main` channel: there are no
# manifests for commits, a hub following a branch is a hub being worked on, and pretending otherwise
# would mean an escape hatch that ends up pasted into a house. And it has no override -- a hub that
# cannot verify a release does not install it.
# A directory, not one file, and that is a decision that cannot be taken later: a hub trusts the keys
# it was installed with and never adds one, because a key arriving from the repository afterwards is
# exactly the push this whole file exists to catch. So a second key has to be there from the first
# install or it can never be there at all -- and without one, losing the first means no hub in any
# house can be updated again, ever. Any key in here may sign a release.
KEYS="${HOME_HUB_KEYS:-/etc/home-hub/release-keys.d}"
RELEASES="${HOME_HUB_RELEASES:-https://github.com/topeysoft/home-hub/releases/download}"

# The manifest's own fields, read with sed. Safe here for one reason only: nothing reads this file
# until openssl has said the maker signed it, so the parser is looking at something our own tool
# wrote rather than at anything a stranger chose.
mf() { sed -n "s/^ *\"$1\": \"\([^\"]*\)\".*/\1/p" "$2" | head -1; }

older_than() {  # older_than A B -> true when A sorts before B by version
  [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" = "$1" ]
}

# verify_release <tag> <dir>
# 0: verified, and VERIFIED_COMMIT / HUB_BRAIN_IMAGE / HUB_IMG_* are set
# 1: could not be verified -- do not install this
# 2: this hub has no key yet, so there is nothing to verify against
# Does any key this hub holds vouch for these bytes?
signed_by_us() {  # file, signature
  local key
  for key in "$KEYS"/*.pub; do
    [ -s "$key" ] || continue
    openssl pkeyutl -verify -pubin -inkey "$key" -rawin -in "$1" -sigfile "$2" >/dev/null 2>&1 && return 0
  done
  return 1
}

held_keys() { ls "$KEYS"/*.pub 2>/dev/null | wc -l | tr -d ' '; }

verify_release() {
  local tag="$1" dir="$2" tmp want got
  [ "$(held_keys)" -gt 0 ] || return 2
  command -v openssl >/dev/null 2>&1 || { echo "  openssl is missing, so a release cannot be checked"; return 1; }
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' RETURN
  if ! curl -fsSL "$RELEASES/$tag/release.json" -o "$tmp/release.json" \
    || ! curl -fsSL "$RELEASES/$tag/release.json.sig" -o "$tmp/release.json.sig"; then
    echo "  $tag has no signed record of what it is, so it is not being installed"; return 1
  fi
  if ! signed_by_us "$tmp/release.json" "$tmp/release.json.sig"; then
    echo "  $tag is not signed by any key this hub trusts, so it is not being installed"; return 1
  fi

  want="$(mf version "$tmp/release.json")"
  [ "$want" = "$tag" ] || { echo "  the signed record says $want and the tag says $tag"; return 1; }

  # The commit the manifest names is what gets checked out, and it has to be the one the tag points
  # at. A tag moved onto another commit fails here, which is the attack this whole file is for.
  VERIFIED_COMMIT="$(mf commit "$tmp/release.json")"
  got="$(git -C "$dir" rev-list -n 1 "$tag" 2>/dev/null)"
  case "$VERIFIED_COMMIT" in
    "$got") : ;;
    *) echo "  $tag points at $got and the signed record says $VERIFIED_COMMIT: the tag has been moved"; return 1 ;;
  esac

  # An upgrade path nobody tested is better refused than discovered in somebody's house.
  local from min
  from="$(git -C "$dir" describe --tags --exact-match 2>/dev/null || echo "")"
  min="$(mf min_from "$tmp/release.json")"
  if [ -n "$from" ] && [ -n "$min" ] && older_than "$from" "$min"; then
    echo "  $tag cannot be installed straight from $from; it wants $min or newer first"; return 1
  fi

  # What to run, by digest. Every image, not only ours: a rented tag is a name upstream can move too.
  HUB_BRAIN_IMAGE="$(mf brain "$tmp/release.json")"
  [ -n "$HUB_BRAIN_IMAGE" ] || { echo "  the signed record names no brain image"; return 1; }
  export HUB_BRAIN_IMAGE
  HUB_IMAGE_VARS=""
  local service ref var
  while read -r service ref; do
    [ -n "$service" ] || continue
    [ "$service" = brain ] && continue      # the brain is named on its own line and pinned above
    var="HUB_IMG_$(echo "$service" | tr 'a-z-' 'A-Z_')"
    export "$var=$ref"
    HUB_IMAGE_VARS="$HUB_IMAGE_VARS $var"
  done <<< "$(sed -n 's/^ *"\([a-z0-9-]*\)": "\([^"]*@sha256:[0-9a-f]*\)".*/\1 \2/p' "$tmp/release.json")"
  export HUB_IMAGE_VARS
  local n; n="$(echo "$HUB_IMAGE_VARS" | wc -w | tr -d ' ')"
  echo "  $tag verified: $(echo "$VERIFIED_COMMIT" | cut -c1-12), $(echo "$HUB_BRAIN_IMAGE" | sed 's/.*@sha256:/brain sha256:/' | cut -c1-26), and $n image$([ "$n" = 1 ] || echo s) pinned by digest"
  return 0
}

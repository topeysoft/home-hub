#!/usr/bin/env bash
# Signing a release, which is the step that decides what may run as root in somebody's house.
#
#   tools/release.sh --new-key        make the keypair, once, ever
#   tools/release.sh v0.3.0           sign that release and attach the record to it
#
# The private key does not live on GitHub and is not in CI. That is the whole point of it: cosign
# keyless on the image build already proves "built by this workflow, from this commit", and it would
# prove exactly that for an attacker who could push to the repository too. This key is the one thing
# somebody who owns the GitHub account still does not have, and it is only worth the inconvenience
# for as long as it stays somewhere GitHub cannot reach. docs/updates.md, piece 2.
#
# Run it after CI has finished publishing the tag's images: the record names them by digest, so the
# digests have to exist. Until it has run, hubs refuse that release rather than install it unchecked,
# which is the right way round but is also a reason not to leave a tag sitting unsigned.
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="${2:-release}"
PRIV="${HOME_HUB_RELEASE_KEY:-$HOME/.home-hub/$NAME-key.pem}"
KEYS="driver-layer/host/release-keys.d"

if [ "${1:-}" = "--new-key" ]; then
  [ -s "$PRIV" ] && { echo "There is already a key at $PRIV. Overwriting it locks out every hub that trusts it."; exit 1; }
  mkdir -p "$(dirname "$PRIV")" "$KEYS"; ( umask 077; openssl genpkey -algorithm ed25519 -out "$PRIV" )
  openssl pkey -in "$PRIV" -pubout -out "$KEYS/$NAME.pub"
  cat <<TEXT

Private key: $PRIV   (0600)
Public key:  $KEYS/$NAME.pub   — commit this; it is what hubs will trust

Three things, and they are the whole security of this:

  * Back the private key up somewhere off this machine and off GitHub. A hub that has
    installed the public half refuses every release the matching private half did not
    sign, so losing it with no second key means no hub in any house can ever be updated
    again.
  * Make a second one NOW if you are ever going to:  $0 --new-key spare
    A hub trusts the keys it was installed with and never adds one -- a key arriving from
    the repository later is exactly the push all of this exists to catch. Keep the spare
    offline, somewhere different, and never sign with it until you have to.
  * Hubs already in houses are not reached by any of this. The keys they hold are the keys
    they had on their first install.

TEXT
  exit 0
fi

TAG="${1:-}"
[ -n "$TAG" ] || { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || { echo "No such tag: $TAG"; exit 1; }
[ -s "$PRIV" ] || { echo "No signing key at $PRIV. Run: $0 --new-key"; exit 1; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
echo "Asking the registries what $TAG actually is..."
python3 tools/release-manifest.py "$TAG" > "$TMP/release.json"

# The image this release names has to be one CI built from this tag, not something pushed to the
# registry by hand. cosign's keyless signature says exactly that, and checking it *here* is what
# lets hubs get away with holding no cosign and no Sigstore root: they trust one ed25519 key, and
# that key is only ever put to a manifest whose image passed this. docs/updates.md, piece 2.
BRAIN="$(sed -n 's/^ *"brain": "\([^"]*\)".*//p' "$TMP/release.json")"
if command -v cosign >/dev/null 2>&1; then
  echo "Checking $TAG built the image it claims..."
  cosign verify "$BRAIN"     --certificate-oidc-issuer https://token.actions.githubusercontent.com     --certificate-identity-regexp "^https://github.com/$(git remote get-url origin | sed -E 's#.*github.com[:/]([^/]+/[^/.]+).*#\1#')/\.github/workflows/brain-image\.yml@refs/tags/$TAG\$"     > /dev/null || { echo "That image was not built by this repository's workflow from $TAG. Not signing it."; exit 1; }
elif [ "${HOME_HUB_SKIP_COSIGN:-}" = 1 ]; then
  echo "cosign is not installed, and HOME_HUB_SKIP_COSIGN=1 says sign anyway. The image is going out unchecked."
else
  echo "cosign is not installed, so where $BRAIN came from cannot be checked."
  echo "Install it (brew install cosign), or set HOME_HUB_SKIP_COSIGN=1 if you know why you are skipping it."
  exit 1
fi
openssl pkeyutl -sign -inkey "$PRIV" -rawin -in "$TMP/release.json" -out "$TMP/release.json.sig"
# Never hand out a signature without checking it against the public half that hubs will hold: a
# mismatched pair is silent here and is a brick in every house.
SIGNER=""
for k in "$KEYS"/*.pub; do
  openssl pkeyutl -verify -pubin -inkey "$k" -rawin -in "$TMP/release.json" -sigfile "$TMP/release.json.sig" >/dev/null 2>&1 \
    && { SIGNER="$k"; break; }
done
[ -n "$SIGNER" ] || { echo "That signature checks against none of the public keys in $KEYS, so no hub would accept it. Not uploading."; exit 1; }
echo "Signed with the key hubs know as $(basename "$SIGNER")."
sed -n '2,12p' "$TMP/release.json"
echo "  ...and the rest"

NOTES="releases/${TAG#v}.md"
if command -v gh >/dev/null 2>&1; then
  gh release upload "$TAG" "$TMP/release.json" "$TMP/release.json.sig" --clobber
  # The release body is the notes file as written. A hub reads the same lines out of it to say what
  # is waiting, where it used to show whatever the last commit subject happened to be; the copy that
  # gets installed comes from inside the image, so these two can never disagree about a release.
  [ -f "$NOTES" ] && gh release edit "$TAG" --notes-file "$NOTES"
  echo "Attached to the $TAG release. Hubs on the release channel can now install it."
else
  cp "$TMP/release.json" "$TMP/release.json.sig" .
  echo "gh is not installed. release.json and release.json.sig are in $(pwd); attach them to the $TAG release by hand."
fi

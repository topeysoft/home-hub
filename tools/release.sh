#!/usr/bin/env bash
# Signing a release, which is the step that decides what may run as root in somebody's house.
#
#   tools/release.sh --new-key        make the keypair, once, ever
#   tools/release.sh --check v0.3.0   say what is not ready yet, and change nothing
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
# The second argument names a key, and only when making one: `--new-key spare`. Reading it
# unconditionally made `--check v0.2.2` go looking for a key called v0.2.2, which is a confusing way
# to be told a key is missing.
if [ "${1:-}" = "--new-key" ]; then NAME="${2:-release}"; else NAME="release"; fi
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

CHECK=""
[ "${1:-}" = "--check" ] && { CHECK=1; shift; }
TAG="${1:-}"
[ -n "$TAG" ] || { sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

# Everything that has to be true before a release can be signed, said all at once. Cutting one is a
# thing a person does rarely and under some pressure, and discovering the five prerequisites one
# failure at a time -- each after a wait on the registry -- is a bad way to spend an evening.
# `--check` stops here; a real run carries on only if nothing is missing.
MISSING=0
# Each check runs inside an `if`, because `set -e` at the top of this file would otherwise make the
# first failing test the last one you hear about -- which is exactly the behaviour this replaces.
check() {  # description, what to do about it, then the command to run
  local desc="$1" fix="$2"; shift 2
  if "$@" >/dev/null 2>&1; then printf '  \033[32m✓\033[0m %s\n' "$desc"
  else printf '  \033[31m✗\033[0m %s\n     %s\n' "$desc" "$fix"; MISSING=$((MISSING + 1)); fi
}
notes_read_like_a_house() {
  [ -f "releases/${TAG#v}.md" ] || return 1
  python3 - "${TAG#v}" <<'PRE'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("rm", "tools/release-manifest.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.read_notes(sys.argv[1])
PRE
}
signed_in_to_github() { command -v gh >/dev/null 2>&1 && gh auth status; }
keys_for_hubs() { ls "$KEYS"/*.pub >/dev/null 2>&1; }
images_are_readable() { python3 tools/release-manifest.py "$TAG"; }

echo "Before signing $TAG:"
check "the tag $TAG exists" \
      "git tag $TAG && git push --tags, then wait for CI to publish its images" \
      git rev-parse -q --verify "refs/tags/$TAG"
check "releases/${TAG#v}.md says what changed, in words a household reads" \
      "write it (releases/README.md has the shape and the rules); a release without one does not ship" \
      notes_read_like_a_house
check "a signing key at $PRIV" \
      "$0 --new-key   — and --new-key spare in the same sitting, because a hub never adds one later" \
      test -s "$PRIV"
check "public keys in $KEYS for hubs to trust" \
      "$0 --new-key writes one; commit it" \
      keys_for_hubs
check "gh, signed in, to attach the record to the release" \
      "brew install gh && gh auth login" \
      signed_in_to_github
check "cosign, to check CI built the image this names" \
      "brew install cosign — or HOME_HUB_SKIP_COSIGN=1 to sign without that assurance" \
      command -v cosign
check "every image this release names is readable on its registry" \
      "usually the brain package being private: make it public, or set GITHUB_TOKEN. See: python3 tools/release-manifest.py $TAG" \
      images_are_readable

if [ -n "$CHECK" ]; then
  if [ "$MISSING" -eq 0 ]; then printf '\nNothing missing. %s %s will sign it.\n' "$0" "$TAG"; exit 0; fi
  printf '\n%s thing(s) to sort out first.\n' "$MISSING"; exit 1
fi
[ "$MISSING" -eq 0 ] || { printf '\n%s thing(s) missing, so nothing has been signed.\n' "$MISSING"; exit 1; }
echo

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
echo "Asking the registries what $TAG actually is..."
python3 tools/release-manifest.py "$TAG" > "$TMP/release.json"

# The image this release names has to be one CI built from this tag, not something pushed to the
# registry by hand. cosign's keyless signature says exactly that, and checking it *here* is what
# lets hubs get away with holding no cosign and no Sigstore root: they trust one ed25519 key, and
# that key is only ever put to a manifest whose image passed this. docs/updates.md, piece 2.
BRAIN="$(sed -n 's/^ *"brain": "\([^"]*\)".*/\1/p' "$TMP/release.json")"
if command -v cosign >/dev/null 2>&1; then
  echo "Checking $TAG built the image it claims..."
  # cosign reads docker's own credentials and knows nothing about gh, so a package that is not public
  # is UNAUTHORIZED to it even when everything else here reads it perfectly well. Hand it the same
  # credential release-manifest.py uses, rather than making somebody `docker login` and leave a
  # registry password sitting in their docker config afterwards.
  #
  # As a username and password, NOT --registry-token: that flag passes the value straight through as
  # the bearer, and ghcr wants a token of its own in exchange for the credential first. With the
  # token flag it gets as far as the signature and then says "DENIED: invalid token", which reads
  # like the signature is bad rather than like nobody has logged in.
  REG_PASS="${GITHUB_TOKEN:-${GH_TOKEN:-${CR_PAT:-$(gh auth token 2>/dev/null || true)}}}"
  REG_USER="$(gh api user -q .login 2>/dev/null || echo x)"
  SLUG="$(git remote get-url origin | sed -E 's#.*github.com[:/]([^/]+/[^/.]+).*#\1#')"
  WHO="^https://github.com/$SLUG/\.github/workflows/brain-image\.yml@refs/tags/$TAG\$"
  if ! cosign verify "$BRAIN" \
      ${REG_PASS:+--registry-username "$REG_USER" --registry-password "$REG_PASS"} \
      --certificate-oidc-issuer https://token.actions.githubusercontent.com \
      --certificate-identity-regexp "$WHO" > /dev/null; then
    echo "That image was not built by this repository's workflow from $TAG. Not signing it."
    exit 1
  fi
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

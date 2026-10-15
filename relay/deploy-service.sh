#!/bin/sh
# Puts a new version of the registration service on the relay box without a new box:
#
#   relay/deploy-service.sh <ref> [payers-file]      e.g. relay/deploy-service.sh origin/development
#   RELAY=root@relay.example relay/deploy-service.sh ...
#
# Builds relay/service at <ref> on the box (from this checkout, so the private repo needs no key there), points
# relay-service.service at that image and restarts only it. Tunnels already up stay up; new logins wait the few
# seconds it takes. A payers file ("name key" lines) goes to the volume first. Going back is the same with the old ref,
# whose image stays on the box. Afterwards relay_service_ref in terraform.tfvars is set to the same commit, so a new box
# would build exactly this.
set -eu
REF=${1:?which commit: relay/deploy-service.sh <ref> [payers-file]}
PAYERS=${2:-}
RELAY=${RELAY:-root@relay.elyir.app}
cd "$(dirname "$0")/.."
SHA=$(git rev-parse --verify "$REF^{commit}")
SSH="ssh -o BatchMode=yes $RELAY"

echo "== build relay-service:$SHA on $RELAY"
git archive --format=tar "$SHA:relay/service" | $SSH "docker build -q -t relay-service:$SHA - >/dev/null"

if [ -n "$PAYERS" ]; then
  echo "== payers"
  $SSH "umask 077 && cat > /var/lib/relay/service/payers.tmp && mv /var/lib/relay/service/payers.tmp /var/lib/relay/service/payers" < "$PAYERS"
fi

echo "== switch and restart"
$SSH sh -s "$SHA" <<'REMOTE'
set -eu
NEW=$1
UNIT=/etc/systemd/system/relay-service.service
OLD=$(grep -o 'relay-service:[0-9a-f]\{40\}' "$UNIT" | head -1 | cut -d: -f2)
[ "$OLD" = "$NEW" ] || sed -i "s/$OLD/$NEW/g" "$UNIT"
systemctl daemon-reload
systemctl restart relay-service
for i in 1 2 3 4 5 6 7 8 9 10; do
  curl -fsS -m 3 http://127.0.0.1:7100/alive >/dev/null 2>&1 && { echo "relay-service $NEW is up (was $OLD)"; exit 0; }
  sleep 2
done
echo "relay-service didn't come up: going back to $OLD" >&2
sed -i "s/$NEW/$OLD/g" "$UNIT"; systemctl daemon-reload; systemctl restart relay-service
exit 1
REMOTE

TFVARS=relay/terraform/terraform.tfvars
if [ -f "$TFVARS" ]; then
  sed -i.bak "s/^relay_service_ref *=.*/relay_service_ref = \"$SHA\"/" "$TFVARS" && rm -f "$TFVARS.bak"
  echo "== $TFVARS: relay_service_ref = $SHA (not applied; a new box would build this)"
fi

#!/bin/sh
# Autoroute what route.py left open, with KiCadRoutingTools.
#
#   ./autoroute.sh out.kicad_pcb        # routes a COPY; never touches puck-revA.kicad_pcb
#
# WHY THESE FLAGS. The tool will happily relax the project's design rules to get a route in, and
# says so loudly -- on the first run here it rewrote min hole 0.3 -> 0.15 mm and min via 0.45 ->
# 0.25 mm, which is under JLC's standard process. Those numbers are a real fab floor, not a
# preference, so --escalation off and --no-fix-drc-settings hold them and the geometry is pinned
# explicitly. Routing then completes with escalations=0.
#
# WHAT IT LEAVES: the USB pair. It boxes in against the CC and +3V3 copper near J1, and forcing it
# through squeezes USB_DM past J1's mounting pegs at 0.218 mm against a 0.25 mm rule. That pair wants
# hand routing anyway -- length-matched, over unbroken ground.
#
# Verify after with ./drc.sh --board <out>, never bare kicad-cli.
set -e
RT="$HOME/Documents/KiCad/10.0/3rdparty/KiCadRoutingTools"
SRC="$(dirname "$0")/puck-revA.kicad_pcb"
OUT="${1:-/tmp/puck-routed.kicad_pcb}"
IN="$(mktemp -t puckXXXX).kicad_pcb"

cp "$SRC" "$IN"
cp "$(dirname "$0")/puck-revA.kicad_pro" "${IN%.kicad_pcb}.kicad_pro"
python3 "$RT/py_router/route.py" "$IN" "$OUT" --nets "*" \
    --escalation off --no-fix-drc-settings \
    --track-width 0.25 --clearance 0.15 --via-size 0.6 --via-drill 0.3
cp "$(dirname "$0")/puck-revA.kicad_pro" "${OUT%.kicad_pcb}.kicad_pro"
echo "routed -> $OUT   (verify: ./drc.sh --board $OUT)"

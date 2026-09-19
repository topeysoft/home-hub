#!/bin/sh
# DRC with zones filled. kicad-cli alone cannot fill them; see kicad_check.py.
exec /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 \
     "$(dirname "$0")/kicad_check.py" "$@" 2>/dev/null

#!/usr/bin/env bash
# Puts hub.elyir.com together in site/dist: the front page, its pictures, and the install script from the top of the
# repository, so /install serves exactly what the README's command does. functions/ stays beside dist, where
# `wrangler pages deploy dist` looks for it.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf dist && mkdir -p dist/shots
cp index.html _headers dist/
cp shots/*.jpg dist/shots/
cp ../app/public/favicon.svg dist/
cp ../install.sh dist/install.sh
echo "site/dist: $(find dist -type f | wc -l | tr -d ' ') files"

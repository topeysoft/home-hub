#!/bin/sh
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This repository is public: no person's name or email, no real printer's name, no home network. Exits 1 and
# lists file:line for each. The copyright notices are the one place the maintainer's name belongs.
#
#   scripts/private-words.sh            every tracked file (ci.yml's secrets job)
#   scripts/private-words.sh --cached   what is staged (.githooks/pre-commit; git config core.hooksPath .githooks)
#
# Printers in examples and tests are Atlas, Juno and Vega; people are Sam and Alex, sam@example.com;
# addresses at home are 192.168.1.x.
WORDS='\b(temi|temitope|adeyeri|obi1|r2d2|c3po|e3dtc|tcscreen|virusbroadcast)\b|temi\.adeyeri|192[.-]168[.-]86[.-]'
hits=$(git grep -n -I -i -P ${1:+"$1"} "$WORDS" -- . ':!scripts/private-words.sh' ':!LICENSE' ':!CLA.md' \
  | grep -v -E 'SPDX-FileCopyrightText: 2026 Temitope Adeyeri|Copyright 2026 Temitope Adeyeri')
[ -z "$hits" ] && exit 0
echo "$hits"
echo "private words in a public repository (above): use Atlas, Juno, Vega; Sam, Alex; 192.168.1.x" >&2
exit 1

# SPDX-FileCopyrightText: 2018-2025 Espressif Systems (Shanghai) CO LTD
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: Apache-2.0
#
# ESPRESSIF'S PROVISIONING CLIENT, VENDORED. The hub is the client for our own door onto a strip
# (design/strip/Ours.dc.html) -- Espressif's phone app is a bench instrument and never ships. This
# is the SRP6a and protobuf half of that client, taken from esp-idf/tools/esp_prov at v5.4.1 because
# it was dropped from the IDF at v6, and writing an SRP6a client to talk to our own SRP6a is not
# work worth doing twice.
#
# Apache-2.0 into AGPL-3.0-or-later is compatible in this direction. The files keep their headers.
# What we changed, and nothing else: proto/__init__.py loads the generated pb2 modules from this
# directory rather than from $IDF_PATH, since a hub has no IDF.

# Upstream ran with this directory itself on sys.path, so every file imports its siblings by bare
# name -- `import proto`, `from security import ...`. Putting the directory back on sys.path is one
# line and leaves those files untouched; rewriting twenty of them to use relative imports would be a
# fork we then have to maintain against Espressif's.
import os as _os
import sys as _sys

_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

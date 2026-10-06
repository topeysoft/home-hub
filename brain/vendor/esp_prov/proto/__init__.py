# SPDX-FileCopyrightText: 2018-2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
#
# Vendored from esp-idf/tools/esp_prov, which stopped shipping with the IDF at v6. Upstream loaded
# these out of $IDF_PATH at import time; a hub has no IDF, so they sit here beside it instead.
#
# THE pb2 FILES ARE UNMODIFIED AND IMPORT EACH OTHER BY BARE NAME -- `import constants_pb2`, not a
# relative import -- which is why they are registered under those names in sys.modules rather than
# imported as a package. Order matters: a file must be in sys.modules before anything that needs it.
import importlib.util
import os
import sys
from typing import Any

_here = os.path.dirname(os.path.abspath(__file__))


def _load(name: str) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, os.path.join(_here, name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


constants_pb2 = _load('constants_pb2')
sec0_pb2 = _load('sec0_pb2')
sec1_pb2 = _load('sec1_pb2')
sec2_pb2 = _load('sec2_pb2')
session_pb2 = _load('session_pb2')
wifi_constants_pb2 = _load('wifi_constants_pb2')
wifi_config_pb2 = _load('wifi_config_pb2')
wifi_ctrl_pb2 = _load('wifi_ctrl_pb2')
wifi_scan_pb2 = _load('wifi_scan_pb2')

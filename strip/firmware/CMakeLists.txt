# A light strip controller, on ESP-IDF and esp-matter.
#
# It was a PlatformIO/Arduino project until the hardware settled it: the Arduino framework ships its
# Matter libraries with CONFIG_ENABLE_CHIPOBLE unset on every target, so a strip built that way can
# never advertise itself for commissioning -- it has to be on the Wi-Fi already. Which means a
# household with an Apple TV and no hub of ours could not set one up at all, and that is the promise
# this product line started from. docs/strip.md has the scans from both builds.
#
#     . ~/esp/esp-idf-v6.0.2/export.sh && . ~/esp/esp-matter/export.sh
#     idf.py set-target esp32s3
#     idf.py build flash monitor
#
# The shape below follows esp-matter's own examples rather than being invented, which the first
# attempt was and which cost a build.
cmake_minimum_required(VERSION 3.16)

if(NOT DEFINED ENV{ESP_MATTER_PATH})
    message(FATAL_ERROR "ESP_MATTER_PATH is not set. Run: . ~/esp/esp-matter/export.sh")
endif()

if(NOT DEFINED ENV{ESP_MATTER_DEVICE_PATH})
    set(ENV{ESP_MATTER_DEVICE_PATH} $ENV{ESP_MATTER_PATH}/device_hal/device/esp32s3_devkit_c)
endif()

set(PROJECT_VER "0.3.0")
set(ESP_MATTER_PATH $ENV{ESP_MATTER_PATH})
set(MATTER_SDK_PATH ${ESP_MATTER_PATH}/connectedhomeip/connectedhomeip)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
include(${ESP_MATTER_PATH}/examples/common/cmake_common/components_include.cmake)
include($ENV{ESP_MATTER_DEVICE_PATH}/esp_matter_device.cmake)

set(EXTRA_COMPONENT_DIRS
    "${ESP_MATTER_PATH}/examples/common"
    "${MATTER_SDK_PATH}/config/esp32/components"
    "${ESP_MATTER_PATH}/components"
    "${ESP_MATTER_PATH}/device_hal/device"
    ${extra_components_dirs_append})

project(strip)

idf_build_set_property(CXX_COMPILE_OPTIONS "-std=gnu++17;-Os;-DCHIP_HAVE_CONFIG_H;-Wno-overloaded-virtual" APPEND)
idf_build_set_property(C_COMPILE_OPTIONS "-Os" APPEND)
idf_build_set_property(COMPILE_OPTIONS "-Wno-format-nonliteral;-Wno-format-security" APPEND)

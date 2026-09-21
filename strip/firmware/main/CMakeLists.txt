idf_component_register(SRC_DIRS "." PRIV_INCLUDE_DIRS ".")
target_compile_options(${COMPONENT_LIB} PRIVATE "-DCHIP_HAVE_CONFIG_H")

# Forwarded so `idf.py -DDATA_PIN=21 build` means what the README says it means. idf.py's -D sets a
# CMake variable and nothing more -- without this it is accepted, ignored, and the board is flashed
# with the old pin, which is the worst kind of wrong because it looks like it worked.
foreach(opt DATA_PIN BUTTON_PIN SELFTEST)
    # NOT just DEFINED: `idf.py -DDATA_PIN= build` defines it as an empty string, which compiles to
    # `#define DATA_PIN` and then fails deep inside esp_log.h with nothing that names the cause.
    if(DEFINED ${opt} AND NOT "${${opt}}" STREQUAL "")
        target_compile_definitions(${COMPONENT_LIB} PRIVATE ${opt}=${${opt}})
    endif()
endforeach()

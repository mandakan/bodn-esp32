set(IDF_TARGET esp32s3)

# For external boards, sdkconfig paths must be absolute because CMakeLists.txt
# resolves them with file(READ) from the port directory.
get_filename_component(_PORT_DIR ${CMAKE_CURRENT_LIST_DIR}/../../micropython/ports/esp32 ABSOLUTE)

# Deliberately do NOT include sdkconfig.ble — the firmware never imports
# `bluetooth`, so pulling in the NimBLE stack (200–300 KB) is pure waste.
# Run `tools/size-review.py` after changing this list.
set(SDKCONFIG_DEFAULTS
    ${_PORT_DIR}/boards/sdkconfig.base
    ${_PORT_DIR}/boards/sdkconfig.spiram_sx
    ${_PORT_DIR}/boards/sdkconfig.spiram_oct
    ${CMAKE_CURRENT_LIST_DIR}/sdkconfig.board
)

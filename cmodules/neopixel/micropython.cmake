add_library(usermod_neopixel INTERFACE)

target_sources(usermod_neopixel INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/neopixel_mod.c
    ${CMAKE_CURRENT_LIST_DIR}/engine.c
    ${CMAKE_CURRENT_LIST_DIR}/patterns.c
)

target_include_directories(usermod_neopixel INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(usermod INTERFACE usermod_neopixel)

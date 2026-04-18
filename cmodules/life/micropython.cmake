add_library(usermod_life INTERFACE)

target_sources(usermod_life INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/life_mod.c
    ${CMAKE_CURRENT_LIST_DIR}/life.c
)

target_include_directories(usermod_life INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(usermod INTERFACE usermod_life)

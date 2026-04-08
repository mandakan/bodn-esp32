add_library(usermod_audiomix INTERFACE)

target_sources(usermod_audiomix INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/audiomix.c
    ${CMAKE_CURRENT_LIST_DIR}/mixer.c
    ${CMAKE_CURRENT_LIST_DIR}/ringbuf.c
    ${CMAKE_CURRENT_LIST_DIR}/tonegen.c
)

target_include_directories(usermod_audiomix INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(usermod INTERFACE usermod_audiomix)

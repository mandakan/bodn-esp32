add_library(usermod_draw INTERFACE)

target_sources(usermod_draw INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/draw.c
    ${CMAKE_CURRENT_LIST_DIR}/decode.c
    ${CMAKE_CURRENT_LIST_DIR}/font_render.c
    ${CMAKE_CURRENT_LIST_DIR}/blit.c
    ${CMAKE_CURRENT_LIST_DIR}/primitives.c
)

target_include_directories(usermod_draw INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(usermod INTERFACE usermod_draw)

add_library(usermod_mcpinput INTERFACE)

target_sources(usermod_mcpinput INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/mcpinput.c
    ${CMAKE_CURRENT_LIST_DIR}/scanner.c
)

target_include_directories(usermod_mcpinput INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(usermod INTERFACE usermod_mcpinput)

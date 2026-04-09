add_library(usermod_spidma INTERFACE)

target_sources(usermod_spidma INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/spidma.c
)

target_include_directories(usermod_spidma INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(usermod INTERFACE usermod_spidma)

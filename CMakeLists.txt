cmake_minimum_required(VERSION 3.28)

project(Genseki VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(genseki_cxx26_flags INTERFACE)
target_compile_options(genseki_cxx26_flags INTERFACE
    $<$<CXX_COMPILER_ID:GNU>:-std=c++2c>
    $<$<CXX_COMPILER_ID:Clang>:-std=c++2c>
)

add_library(genseki_core
    src/core/board.cpp
    src/core/uhp.cpp
)
target_include_directories(genseki_core PUBLIC include)
target_link_libraries(genseki_core PUBLIC genseki_cxx26_flags)

include(CTest)
find_package(Python3 COMPONENTS Interpreter)
find_program(CARGO_EXECUTABLE cargo REQUIRED)
add_subdirectory(Alpha)

# The public executable is the flagship itself, not the retired league engine.
set(GENSEKI_ALPHA_EXE ${CMAKE_BINARY_DIR}/genseki${CMAKE_EXECUTABLE_SUFFIX})
add_custom_command(OUTPUT ${GENSEKI_ALPHA_EXE}
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${CMAKE_BINARY_DIR}/rust-target/release/alpha_nokamute_mit${CMAKE_EXECUTABLE_SUFFIX}
        ${GENSEKI_ALPHA_EXE}
    DEPENDS alpha_nokamute_mit
        ${CMAKE_BINARY_DIR}/rust-target/release/alpha_nokamute_mit${CMAKE_EXECUTABLE_SUFFIX}
)
add_custom_target(genseki ALL DEPENDS ${GENSEKI_ALPHA_EXE})

# Rho uses position/child enumeration, not a second evaluation/search engine.
add_executable(genseki_rules src/main.cpp)
target_link_libraries(genseki_rules PRIVATE genseki_core)

enable_testing()
add_executable(genseki_tests tests/core_tests.cpp)
target_link_libraries(genseki_tests PRIVATE genseki_core)
add_test(NAME genseki_core_tests COMMAND genseki_tests)
if(Python3_Interpreter_FOUND)
    add_test(NAME genseki_default_engine
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/default_engine.py
            ${GENSEKI_ALPHA_EXE}
            ${CMAKE_BINARY_DIR}/rust-target/release/alpha_nokamute_mit${CMAKE_EXECUTABLE_SUFFIX})
endif()

add_subdirectory(Nu)

if(WIN32)
    add_executable(genseki_gui WIN32 src/gui/win32_gui.cpp)
    target_compile_definitions(genseki_gui PRIVATE
        UNICODE
        _UNICODE
        NOMINMAX
        WIN32_LEAN_AND_MEAN
    )
    set_target_properties(genseki_gui PROPERTIES CXX_SCAN_FOR_MODULES OFF)
    target_link_libraries(genseki_gui PRIVATE gdi32 user32 comdlg32 shell32)
    add_dependencies(genseki_gui genseki)
endif()

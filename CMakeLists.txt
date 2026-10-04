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
    src/core/bot.cpp
)
target_include_directories(genseki_core PUBLIC include)
target_link_libraries(genseki_core PUBLIC genseki_cxx26_flags)

add_executable(genseki src/main.cpp)
target_link_libraries(genseki PRIVATE genseki_core)

enable_testing()
add_executable(genseki_tests tests/core_tests.cpp)
target_link_libraries(genseki_tests PRIVATE genseki_core)
add_test(NAME genseki_core_tests COMMAND genseki_tests)

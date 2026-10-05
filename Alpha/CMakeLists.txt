cmake_minimum_required(VERSION 3.25)
project(alpha_nokamute LANGUAGES CXX)
# CMake 3.29 does not yet know CXX26; the explicit compiler flag below selects it.
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_executable(alpha_nokamute src/main.cpp)

find_program(CARGO_EXECUTABLE cargo)
if(CARGO_EXECUTABLE)
  set(ALPHA_MIT_EXE ${CMAKE_BINARY_DIR}/rust-target/release/alpha_nokamute_mit${CMAKE_EXECUTABLE_SUFFIX})
  file(GLOB_RECURSE ALPHA_MIT_SOURCES CONFIGURE_DEPENDS
    ${CMAKE_CURRENT_SOURCE_DIR}/vendor/nokamute/src/*.rs
    ${CMAKE_CURRENT_SOURCE_DIR}/vendor/minimax-rs/src/*.rs)
  add_custom_command(OUTPUT ${ALPHA_MIT_EXE}
    COMMAND ${CARGO_EXECUTABLE} build --release -j 1 --locked
            --manifest-path ${CMAKE_CURRENT_SOURCE_DIR}/vendor/nokamute/Cargo.toml
            --target-dir ${CMAKE_BINARY_DIR}/rust-target
    DEPENDS ${ALPHA_MIT_SOURCES}
            ${CMAKE_CURRENT_SOURCE_DIR}/vendor/nokamute/Cargo.toml
            ${CMAKE_CURRENT_SOURCE_DIR}/vendor/minimax-rs/Cargo.toml
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    COMMENT "Building MIT-derived Alpha strength backend")
  add_custom_target(alpha_nokamute_mit ALL DEPENDS ${ALPHA_MIT_EXE})
endif()
if(MSVC)
  target_compile_options(alpha_nokamute PRIVATE /std:c++latest /W4 /O2)
else()
  target_compile_options(alpha_nokamute PRIVATE -std=c++2c -Wall -Wextra -Wpedantic -O2)
endif()

include(CTest)
find_package(Python3 COMPONENTS Interpreter)
if(BUILD_TESTING AND Python3_Interpreter_FOUND)
  add_test(NAME alpha_smoke
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/smoke.py
            $<TARGET_FILE:alpha_nokamute>)
  add_test(NAME alpha_contracts
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/contracts.py
            $<TARGET_FILE:alpha_nokamute>)
  add_test(NAME alpha_modes
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/modes.py
            $<TARGET_FILE:alpha_nokamute>)
  if(CARGO_EXECUTABLE)
    add_test(NAME alpha_mit_backend
      COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/mit_backend.py
              ${ALPHA_MIT_EXE})
  endif()
endif()

cmake_minimum_required(VERSION 3.28)

project(Genseki VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_CXX_SCAN_FOR_MODULES OFF)

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

add_library(genseki_review_rules src/core/board.cpp src/core/uhp.cpp)
target_include_directories(genseki_review_rules PUBLIC include)
target_compile_definitions(genseki_review_rules PUBLIC GENSEKI_NU_CANCELLATION)
target_link_libraries(genseki_review_rules PUBLIC genseki_cxx26_flags)
add_library(genseki_review_core src/review/review.cpp src/review/alpha_process.cpp)
target_link_libraries(genseki_review_core PUBLIC genseki_review_rules)
if(WIN32)
    target_compile_definitions(genseki_review_core PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)
    target_link_libraries(genseki_review_core PUBLIC bcrypt)
endif()
add_executable(genseki_review src/review/main.cpp)
target_link_libraries(genseki_review PRIVATE genseki_review_core)

enable_testing()
add_executable(genseki_tests tests/core_tests.cpp)
target_link_libraries(genseki_tests PRIVATE genseki_core)
add_test(NAME genseki_core_tests COMMAND genseki_tests)
add_executable(genseki_review_tests tests/review_tests.cpp)
target_link_libraries(genseki_review_tests PRIVATE genseki_review_core)
add_test(NAME genseki_review_tests COMMAND genseki_review_tests)
if(WIN32)
    add_executable(genseki_review_fake_alpha tests/review_fake_alpha.cpp)
    target_link_libraries(genseki_review_fake_alpha PRIVATE genseki_cxx26_flags)
    add_executable(genseki_review_transport_tests tests/review_transport_tests.cpp)
    target_link_libraries(genseki_review_transport_tests PRIVATE genseki_review_core)
    add_test(NAME genseki_review_transport COMMAND genseki_review_transport_tests $<TARGET_FILE:genseki_review_fake_alpha>)
    set_tests_properties(genseki_review_transport PROPERTIES TIMEOUT 15 RUN_SERIAL TRUE)
endif()
if(Python3_Interpreter_FOUND)
    add_test(NAME genseki_transport_tests
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/transport_tests.py)
    add_test(NAME genseki_default_engine
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/default_engine.py
            ${GENSEKI_ALPHA_EXE}
            ${CMAKE_BINARY_DIR}/rust-target/release/alpha_nokamute_mit${CMAKE_EXECUTABLE_SUFFIX})
endif()

add_subdirectory(Nu)

if(WIN32)
    enable_language(RC)
    set(GENSEKI_RASTER_DLL ${CMAKE_BINARY_DIR}/genseki_raster.dll)
    add_custom_command(OUTPUT ${GENSEKI_RASTER_DLL}
        COMMAND ${CARGO_EXECUTABLE} build --release --locked -j 1
            --manifest-path ${CMAKE_CURRENT_SOURCE_DIR}/src/gui/raster/Cargo.toml
            --target-dir ${CMAKE_BINARY_DIR}/gui-rust-target
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            ${CMAKE_BINARY_DIR}/gui-rust-target/release/genseki_raster.dll ${GENSEKI_RASTER_DLL}
        DEPENDS src/gui/raster/Cargo.toml src/gui/raster/Cargo.lock src/gui/raster/src/lib.rs)
    add_custom_target(genseki_raster DEPENDS ${GENSEKI_RASTER_DLL})
    add_executable(genseki_gui WIN32 src/gui/win32_gui.cpp src/gui/assets/icons.rc)
    file(GLOB_RECURSE GENSEKI_GUI_ASSETS CONFIGURE_DEPENDS
        ${CMAKE_CURRENT_SOURCE_DIR}/src/gui/assets/*.svg
        ${CMAKE_CURRENT_SOURCE_DIR}/src/gui/assets/*.wav
        ${CMAKE_CURRENT_SOURCE_DIR}/src/gui/assets/*.ttf)
    set_source_files_properties(src/gui/assets/icons.rc PROPERTIES OBJECT_DEPENDS "${GENSEKI_GUI_ASSETS}")
    target_include_directories(genseki_gui PRIVATE src/gui/assets)
    target_compile_definitions(genseki_gui PRIVATE
        UNICODE
        _UNICODE
        NOMINMAX
        WIN32_LEAN_AND_MEAN
    )
    set_target_properties(genseki_gui PROPERTIES CXX_SCAN_FOR_MODULES OFF)
    target_link_libraries(genseki_gui PRIVATE gdi32 user32 comdlg32 comctl32 shell32 ole32 oleaut32 msimg32 winmm genseki_review_core)
    add_dependencies(genseki_gui genseki genseki_raster)
    add_custom_command(TARGET genseki_gui POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_directory
            ${CMAKE_CURRENT_SOURCE_DIR}/src/gui/raster/licenses ${CMAKE_BINARY_DIR}/gui-licenses
        COMMAND ${CMAKE_COMMAND} -E copy
            ${CMAKE_CURRENT_SOURCE_DIR}/src/gui/assets/sounds/NOTICE.md ${CMAKE_BINARY_DIR}/gui-licenses/Chess-Master.md)
    add_custom_command(TARGET genseki_gui POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy
            ${CMAKE_CURRENT_SOURCE_DIR}/src/gui/assets/fonts/OFL.txt ${CMAKE_BINARY_DIR}/gui-licenses/Nunito-OFL.txt
        COMMAND ${CMAKE_COMMAND} -E copy
            ${CMAKE_CURRENT_SOURCE_DIR}/src/gui/assets/fonts/NOTICE.md ${CMAKE_BINARY_DIR}/gui-licenses/Nunito.md)
    add_test(NAME genseki_svg_icons COMMAND genseki_gui --check-icons)
    add_test(NAME genseki_sound_assets COMMAND genseki_gui --check-sounds)
    add_test(NAME genseki_nunito_font COMMAND genseki_gui --check-font)
    add_test(NAME genseki_review_gui COMMAND genseki_gui --check-review ${CMAKE_BINARY_DIR}/review-ui)
    add_test(NAME genseki_review_isolation COMMAND genseki_gui --check-review-isolation)
    add_test(NAME genseki_review_flow COMMAND genseki_gui --check-review-flow ${GENSEKI_ALPHA_EXE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/review_completed.uhp ${CMAKE_BINARY_DIR}/review-flow)
    set_tests_properties(genseki_review_flow PROPERTIES TIMEOUT 180 RUN_SERIAL TRUE)
    set_tests_properties(genseki_review_gui PROPERTIES TIMEOUT 20)
endif()

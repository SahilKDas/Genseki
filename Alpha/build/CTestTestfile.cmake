# CMake generated Testfile for 
# Source directory: ._/Workspace_______/Genseki/Alpha
# Build directory: ._/Workspace_______/Genseki/Alpha/build
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test([=[alpha_smoke]=] "._/Users/user_/AppData/Local/Programs/Python/Python313/python.exe" "._/Workspace_______/Genseki/Alpha/tests/smoke.py" "._/Workspace_______/Genseki/Alpha/build/alpha_nokamute.exe")
set_tests_properties([=[alpha_smoke]=] PROPERTIES  _BACKTRACE_TRIPLES "._/Workspace_______/Genseki/Alpha/CMakeLists.txt;34;add_test;._/Workspace_______/Genseki/Alpha/CMakeLists.txt;0;")
add_test([=[alpha_contracts]=] "._/Users/user_/AppData/Local/Programs/Python/Python313/python.exe" "._/Workspace_______/Genseki/Alpha/tests/contracts.py" "._/Workspace_______/Genseki/Alpha/build/alpha_nokamute.exe")
set_tests_properties([=[alpha_contracts]=] PROPERTIES  _BACKTRACE_TRIPLES "._/Workspace_______/Genseki/Alpha/CMakeLists.txt;37;add_test;._/Workspace_______/Genseki/Alpha/CMakeLists.txt;0;")
add_test([=[alpha_modes]=] "._/Users/user_/AppData/Local/Programs/Python/Python313/python.exe" "._/Workspace_______/Genseki/Alpha/tests/modes.py" "._/Workspace_______/Genseki/Alpha/build/alpha_nokamute.exe")
set_tests_properties([=[alpha_modes]=] PROPERTIES  _BACKTRACE_TRIPLES "._/Workspace_______/Genseki/Alpha/CMakeLists.txt;40;add_test;._/Workspace_______/Genseki/Alpha/CMakeLists.txt;0;")
add_test([=[alpha_mit_backend]=] "._/Users/user_/AppData/Local/Programs/Python/Python313/python.exe" "._/Workspace_______/Genseki/Alpha/tests/mit_backend.py" "._/Workspace_______/Genseki/Alpha/build/rust-target/release/alpha_nokamute_mit.exe")
set_tests_properties([=[alpha_mit_backend]=] PROPERTIES  _BACKTRACE_TRIPLES "._/Workspace_______/Genseki/Alpha/CMakeLists.txt;44;add_test;._/Workspace_______/Genseki/Alpha/CMakeLists.txt;0;")

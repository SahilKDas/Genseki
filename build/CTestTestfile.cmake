# CMake generated Testfile for 
# Source directory: ._/Workspace_______/Genseki
# Build directory: ._/Workspace_______/Genseki/build
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test([=[genseki_core_tests]=] "._/Workspace_______/Genseki/build/genseki_tests.exe")
set_tests_properties([=[genseki_core_tests]=] PROPERTIES  _BACKTRACE_TRIPLES "._/Workspace_______/Genseki/CMakeLists.txt;45;add_test;._/Workspace_______/Genseki/CMakeLists.txt;0;")
add_test([=[genseki_default_engine]=] "._/Users/user_/AppData/Local/Programs/Python/Python313/python.exe" "._/Workspace_______/Genseki/tests/default_engine.py" "._/Workspace_______/Genseki/build/genseki.exe" "._/Workspace_______/Genseki/build/rust-target/release/alpha_nokamute_mit.exe")
set_tests_properties([=[genseki_default_engine]=] PROPERTIES  _BACKTRACE_TRIPLES "._/Workspace_______/Genseki/CMakeLists.txt;47;add_test;._/Workspace_______/Genseki/CMakeLists.txt;0;")
subdirs("Alpha")

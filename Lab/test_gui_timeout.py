"""Exercise the actual GUI transport against a deliberately late UHP reply."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root/'src/gui/win32_gui.cpp').read_text(encoding='utf-8')
start = source.index('class EngineProcess {')
end = source.index('\n};', start) + len('\n};')
code = r'''
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <filesystem>
#include <optional>
#include <string>
#include <vector>
#include <iostream>
''' + source[start:end] + r'''
int main(int argc, char** argv) {
    if (argc == 1) {
        std::cout << "id fake\nok\n" << std::flush;
        std::string line;
        while (std::getline(std::cin, line)) {
            if (line == "exit") return 0;
            Sleep(6000);
            std::cout << "late response\nok\n" << std::flush;
        }
        return 0;
    }
    EngineProcess engine;
    if (!engine.start(std::filesystem::absolute(argv[0]))) return 1;
    auto first = engine.command("slow");
    if (first.empty() || !first.back().starts_with("err ")) return 2;
    auto second = engine.command("next");
    if (second.size() != 1 || second[0].find("connection is closed") == std::string::npos) return 3;
    return 0;
}
'''
with tempfile.TemporaryDirectory(dir=root/'Lab') as folder:
    cpp, exe = Path(folder)/'timeout.cpp', Path(folder)/'timeout.exe'
    cpp.write_text(code, encoding='utf-8')
    subprocess.run(['g++', '-std=c++23', str(cpp), '-o', str(exe)], check=True, timeout=60)
    subprocess.run([str(exe), 'test'], check=True, timeout=15)
print('GUI timeout regression passed')

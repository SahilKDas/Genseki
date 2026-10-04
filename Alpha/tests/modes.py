"""Black-box checks for Alpha's standalone executable modes."""
import subprocess
import sys


def run(path, *args):
    return subprocess.run([path, *args], check=True, text=True,
                          capture_output=True, timeout=15).stdout


def main(path):
    assert run(path, "perft", "0").strip() == "1"
    assert run(path, "perft", "3").strip() == "1440"
    divide = run(path, "perft", "2", "Base", "--divide").splitlines()
    assert divide[-1] == "total 96"
    debug = run(path, "uhp-debug", "Base", "2")
    assert "legal 4" in debug and "perft 2 96" in debug and "status ok" in debug
    play = run(path, "play", "2", "0.005", "Base")
    assert "result InProgress plies=2" in play


if __name__ == "__main__":
    main(sys.argv[1])

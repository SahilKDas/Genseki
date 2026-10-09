"""Black-box UHP contracts for Alpha's stable public surface."""

import subprocess
import sys


def response(proc, command):
    proc.stdin.write(command + "\n")
    proc.stdin.flush()
    lines = []
    while True:
        line = proc.stdout.readline()
        if not line:
            raise AssertionError(f"engine exited during {command!r}")
        line = line.rstrip("\r\n")
        if line == "ok":
            return lines
        lines.append(line)


def main(path):
    with subprocess.Popen(
        [path, "uhp"], text=True, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ) as proc:
        assert proc.stdout.readline().strip() == "id alpha_nokamute 0.1"
        assert proc.stdout.readline().strip() == "Mosquito;Ladybug;Pillbug"
        assert proc.stdout.readline().strip() == "ok"

        assert response(proc, "validmoves") == ["err game not started"]
        options = response(proc, "options")
        assert options == [
            "Aggression;int;50;50;0;100",
            "BackgroundPondering;bool;False;False",
            "NumThreads;int;1;1;1;12",
            "RandomOpening;bool;False;False",
            "TableSizeMiB;int;64;64;1;4096",
            "Verbose;bool;False;False",
        ]
        assert response(proc, "options set TableSizeMiB 2") == [
            "TableSizeMiB;int;2;64;1;4096"
        ]
        assert response(proc, "options set NumThreads 12") == [
            "NumThreads;int;12;1;1;12"
        ]
        assert response(proc, "options set BackgroundPondering True") == [
            "BackgroundPondering;bool;True;False"
        ]
        assert response(proc, "options set RandomOpening True") == [
            "RandomOpening;bool;True;False"
        ]
        assert response(proc, "options set Aggression 101")[0].startswith("err ")
        assert response(proc, "options set Aggression 50junk")[0].startswith("err ")
        assert response(proc, "newgame Base+P") == ["Base+P;NotStarted;White[1]"]
        assert response(proc, "perft 0") == ["1"]
        assert response(proc, "perft 1 trailing")[0].startswith("err ")
        random_move = response(proc, "bestmove seconds 0.005")[0]
        assert random_move in response(proc, "validmoves")[0].split(";")
        assert response(proc, "unknown") == ["err unrecognized command"]
        proc.stdin.write("exit\n")
        proc.stdin.flush()
        assert proc.wait(timeout=3) == 0


if __name__ == "__main__":
    main(sys.argv[1])

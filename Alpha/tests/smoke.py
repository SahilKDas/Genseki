"""Bounded UHP and move-notation checks for the isolated Alpha executable."""
import subprocess
import sys


def exchange(proc, command):
    proc.stdin.write(command + "\n")
    proc.stdin.flush()
    lines = []
    while True:
        line = proc.stdout.readline().rstrip("\r\n")
        if not line:
            raise AssertionError(f"engine ended during {command!r}")
        if line == "ok":
            return lines
        lines.append(line)


def main(path):
    with subprocess.Popen([path, "uhp"], text=True, stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        assert proc.stdout.readline().startswith("id alpha_nokamute ")
        assert proc.stdout.readline().strip() == "Mosquito;Ladybug;Pillbug"
        assert proc.stdout.readline().strip() == "ok"
        assert exchange(proc, "newgame") == ["Base;NotStarted;White[1]"]
        assert len(exchange(proc, "validmoves")[0].split(";")) == 4
        opening_moves = exchange(proc, "validmoves")
        assert exchange(proc, "perft 0") == ["1"]
        assert exchange(proc, "perft 1") == ["4"]
        assert exchange(proc, "perft 2") == ["96"]
        assert exchange(proc, "validmoves") == opening_moves
        assert exchange(proc, "newgame Base;NotStarted;White[1]") == [
            "Base;NotStarted;White[1]"
        ]
        last = None
        for ply in range(8):
            moves = exchange(proc, "validmoves")[0].split(";")
            assert moves and moves[0] != "", ply
            if ply in (6, 7):
                assert all(m[1] == "Q" for m in moves if m != "pass"), moves
            move = next((m for m in moves if m != "pass" and m[1] != "Q"), moves[0])
            result = exchange(proc, "play " + move)
            assert len(result) == 1 and result[0].startswith("Base;"), (move, result)
            last = result[0]
        assert exchange(proc, "newgame " + last) == [last]
        assert len(exchange(proc, "undo 2")) == 1
        assert exchange(proc, "options set NumThreads 2") == ["NumThreads;int;2;1;1;12"]
        before_search = exchange(proc, "newgame")[0]
        best = exchange(proc, "bestmove depth 2")[0]
        assert best in exchange(proc, "validmoves")[0].split(";")
        info = exchange(proc, "alpha-searchinfo")[0]
        assert "depth=2" in info and "nodes=" in info and " pv=" in info
        assert info.split(" pv=", 1)[1].split("|", 1)[0] == best
        assert exchange(proc, "newgame " + before_search) == [before_search]
        timed = exchange(proc, "bestmove time 00:00:00.010")[0]
        assert timed in exchange(proc, "validmoves")[0].split(";")
        timed_info = exchange(proc, "alpha-searchinfo")[0]
        assert "depth=" in timed_info and "seconds=" in timed_info
        proc.stdin.write("exit\n")
        proc.stdin.flush()
        assert proc.wait(timeout=3) == 0


if __name__ == "__main__":
    main(sys.argv[1])

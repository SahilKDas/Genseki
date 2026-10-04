"""Public UHP smoke test for the exact MIT-derived strength backend."""
import subprocess
import sys


def response(proc, command):
    proc.stdin.write(command + "\n")
    proc.stdin.flush()
    lines = []
    while True:
        line = proc.stdout.readline().rstrip("\r\n")
        if not line:
            raise AssertionError(f"backend ended during {command!r}")
        if line == "ok":
            return lines
        lines.append(line)


def main(path):
    with subprocess.Popen([path, "uhp"], text=True, stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        assert proc.stdout.readline().startswith("id alpha_nokamute_mit 1.0.3+mit.c9ab65e")
        assert proc.stdout.readline().strip() == "Mosquito;Ladybug;Pillbug"
        assert proc.stdout.readline().strip() == "ok"
        assert response(proc, "newgame Base") == ["Base;NotStarted;White[1]"]
        moves = response(proc, "validmoves")[0].split(";")
        assert len(moves) == 4
        assert response(proc, "options get Aggression") == ["Aggression;int;3;3;1;5"]
        assert response(proc, "options set NumThreads 12") == ["NumThreads;int;12;12;1;12"]
        move = response(proc, "bestmove seconds 0.010")[0]
        assert move in moves
        proc.stdin.write("exit\n");proc.stdin.flush()
        assert proc.wait(timeout=3) == 0


if __name__ == "__main__":
    main(sys.argv[1])

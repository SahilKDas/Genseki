"""Compare bounded UHP games with pinned Rust Nokamute.

Both engines receive identical move strings. A difference in canonical notation or
move count is reported with the replayable game log.
"""
import subprocess
import sys
import random


class Engine:
    def __init__(self, path):
        self.proc = subprocess.Popen([path, "uhp"], text=True, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.command("")  # consume startup banner

    def command(self, line):
        if line:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
        lines = []
        while True:
            item = self.proc.stdout.readline()
            if not item:
                raise RuntimeError("engine ended: " + repr(line))
            item = item.rstrip("\r\n")
            if item == "ok":
                return lines
            lines.append(item)

    def close(self):
        self.proc.stdin.write("exit\n")
        self.proc.stdin.flush()
        self.proc.wait(timeout=3)


def main(cpp, rust):
    a, b = Engine(cpp), Engine(rust)
    try:
        for game_type in ("Base", "Base+MLP"):
          for seed in range(8):
            rng = random.Random(seed)
            a.command("newgame " + game_type)
            b.command("newgame " + game_type)
            trace = []
            for ply in range(40):
                am = set(a.command("validmoves")[0].split(";"))
                bm = set(b.command("validmoves")[0].split(";"))
                if am != bm:
                    print("DIFF", game_type, ply, "cpp-only", sorted(am-bm)[:12],
                          "rust-only", sorted(bm-am)[:12])
                    print("moves:", trace)
                    return 1
                if am == {""}:
                    print("MATCH", game_type, "seed", seed, "terminal at", ply)
                    break
                moves = sorted(am)
                # Deterministic, varied, and inexpensive game trajectory.
                move = rng.choice(moves)
                trace.append(move)
                ar = a.command("play " + move)
                br = b.command("play " + move)
                if ar != br:
                    print("STATE DIFF", game_type, ply, move, ar, br)
                    return 1
            else:
                print("MATCH", game_type, "seed", seed, "40 plies")
        return 0
    finally:
        a.close()
        b.close()


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))

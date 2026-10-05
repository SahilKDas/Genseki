"""The public executable must be Alpha, including its default UHP entry point."""
import hashlib
import subprocess
import sys
from pathlib import Path


public, alpha = map(Path, sys.argv[1:3])
assert hashlib.sha256(public.read_bytes()).digest() == hashlib.sha256(alpha.read_bytes()).digest()
proc = subprocess.run([str(public.resolve())], input=(
    "newgame Base\noptions set NumThreads 1\nvalidmoves\n"
    "bestmove time 00:00:00.020\nexit\n"), text=True, capture_output=True, timeout=10)
assert proc.returncode == 0, proc.stderr
blocks = [block.strip().splitlines() for block in proc.stdout.split("ok\n") if block.strip()]
assert len(blocks) == 5, proc.stdout
assert blocks[0][0].startswith("id alpha_nokamute_mit"), blocks[0]
assert blocks[1] == ["Base;NotStarted;White[1]"]
assert blocks[3][0].split(";") and len(blocks[3][0].split(";")) == 4
assert blocks[4][0] in blocks[3][0].split(";"), blocks[4]
print("Public default is Alpha; timed UHP move is legal.")

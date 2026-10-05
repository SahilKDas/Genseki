"""Collect component and split-depth timings on the frozen paired corpus."""
import argparse
import json
import re
import subprocess
from pathlib import Path

from gauntlet import digest

parser = argparse.ArgumentParser()
parser.add_argument("--engine", type=Path, required=True)
parser.add_argument("--corpus", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
exe = str(args.engine.resolve())
records = []
for item in json.loads(args.corpus.read_text(encoding="utf-8"))["records"]:
    position = item["position"]
    proc = subprocess.run([exe, "profile", position], text=True, capture_output=True,
                          check=True, timeout=10)
    components = dict(line.split() for line in proc.stdout.splitlines())
    searches = []
    for cutoff in (1, 2, 3):
        for trial in range(3):
            proc = subprocess.run([exe, "profile-search", position, "4", "2", str(cutoff)],
                                  text=True, capture_output=True, check=True, timeout=30)
            scores = re.findall(r"depth=\s*4,.*?returned\s*(-?\d+)", proc.stderr)
            searches.append({"cutoff": cutoff, "trial": trial,
                             "stdout": proc.stdout, "stderr": proc.stderr,
                             "root_score": int(scores[-1]) if scores else None})
    records.append({"position": position, "components": components, "searches": searches})
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps({"sha256": digest(args.engine), "records": records}, indent=2)
                       + "\n", encoding="utf-8")
print(f"Profiled {len(records)} positions; default cutoff unchanged.")

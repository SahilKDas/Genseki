import argparse
import json
from pathlib import Path

from .core import Replay, digest, folder_bytes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, default=Path('Rho'))
    args = parser.parse_args()
    state = json.loads((args.workspace/'state.json').read_text())
    state['canonical_sha256'] = digest(args.workspace/'champion'/'rho.pt')
    state['canonical_matches_manifest'] = state['canonical_sha256'] == state['champion']['sha256']
    state['workspace_bytes'] = folder_bytes(args.workspace)
    index = json.loads((args.workspace/'replay'/'index.json').read_text())
    state['replay_positions'] = sum(s['positions'] for s in index)
    print(json.dumps(state, indent=2))


if __name__ == '__main__':
    main()

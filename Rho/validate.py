"""Read-only artifact verification; regenerate retained implementation summary."""
import json
from pathlib import Path

from genseki.rho.core import Replay, digest, folder_bytes, load_model, write_json, atomic


def main():
    root = Path('Rho')
    state = json.loads((root/'state.json').read_text())
    model, metadata = load_model(root/'champion'/'rho.pt')
    model_hash = digest(root/'champion'/'rho.pt')
    assert model_hash == state['champion']['sha256']
    for entry in state['lineage']:
        assert digest(root/entry['checkpoint']) == entry['sha256']
        load_model(root/entry['checkpoint'])
    candidate, candidate_metadata = load_model(root/'challenger'/'rho.pt')
    replay = Replay(root/'replay', 200000)
    runs = [json.loads(p.read_text()) for p in sorted((root/'reports').glob('campaign-*.json'))]
    tests = (root/'reports'/'test-results.txt').read_text(encoding='utf-8-sig')
    native_tests = (root/'reports'/'native-test-results.txt').read_text(encoding='utf-8-sig')
    result = dict(champion=state['champion'], model_metadata=metadata,
                  parameter_count=sum(p.numel() for p in model.parameters()),
                  canonical_sha256=model_hash, latest_candidate_generation=candidate_metadata['generation'],
                  replay_positions=replay.size, replay_shards=len(replay.items),
                  totals=state['totals'], reload_and_lineage_hashes_verified=True,
                  completed_arenas=[dict(generation=a['generation'], status=a['status'],
                                         score=a['arena']['score'], wins=a['arena']['wins'],
                                         draws=a['arena']['draws'], losses=a['arena']['losses'])
                                    for a in state['attempts'] if 'arena' in a],
                  campaigns=[dict(id=r['id'], status=r['status'], elapsed_seconds=r['elapsed_seconds'],
                                  config=r['config'], resources=r['resources'], aborted_work=r['aborted_work'])
                             for r in runs],
                  test_output_sha256=digest(root/'reports'/'test-results.txt'),
                  tests_passed='\nOK' in tests.replace('\r',''),
                  native_tests_passed='100% tests passed' in native_tests,
                  workspace_bytes=folder_bytes(root))
    write_json(root/'reports'/'verification.json', result)
    peaks = {key: max(r['resources'].get(key, 0) for r in runs) for key in
             ('peak_disk_bytes', 'peak_gpu_allocated_bytes', 'peak_gpu_reserved_bytes', 'peak_process_ram_bytes')}
    minimum_ram = min(r['resources']['minimum_available_ram_bytes'] for r in runs
                      if r['resources']['minimum_available_ram_bytes'] is not None)
    lines = [
        '# Rho implementation and smoke validation', '',
        'Actual smoke/development evidence. No overnight training or strength improvement claim.', '',
        f"Current champion: trained G0, {result['parameter_count']:,} parameters, SHA-256 `{model_hash}`.", '',
        f"Self-play: {state['totals']['selfplay_games']} games, {replay.size} replay positions; "
        f"{state['totals']['natural_games']} natural result, {state['totals']['capped_games']} capped games.", '',
        'The G0 bootstrap trained policy on capped self-play. Its value head remains without terminal supervision. '
        'G2, G3 and G6 received actual terminal value labels. G6 used two worker lanes, 64 simulations, '
        'CUDA, batch 128, and a game-separated split keeping terminal examples in training. '
        'Only one terminal game exists, so independent terminal value validation is unavailable.', '',
        'Every completed two-game paired arena scored 50% (two capped draws); all challengers were rejected. '
        'Champion bytes match the original trained bootstrap. The retained latest candidate is G6.', '',
        'A Windows ctypes monitoring race stopped the first two-worker run. It was fixed and its failed campaign '
        'JSON/Markdown retained. The subsequent two-worker runs passed. No real OOM occurred; batch backoff '
        'was tested with an explicitly injected unit-test OOM.', '',
        f"Observed peak tensor allocation: {peaks['peak_gpu_allocated_bytes']/1024**2:.1f} MiB; "
        f"reserved: {peaks['peak_gpu_reserved_bytes']/1024**2:.1f} MiB; "
        f"main-process working-set peak: {peaks['peak_process_ram_bytes']/1024**3:.2f} GiB. "
        f"Minimum observed available RAM: {minimum_ram/1024**3:.2f} GiB. "
        f"Workspace at verification: {result['workspace_bytes']/1024**2:.2f} MiB.", '',
        'Tests: see test-results.txt and native-test-results.txt for exact final counts and results. '
        'Safety coverage includes promotion byte preservation, corruption detection, state recovery, '
        'interrupted arena, a real native-worker deadline, parallel resource checks, and injected OOM recovery.', '',
        'Unvalidated: eight-hour endurance; full 160-ply/64-simulation throughput; genuine playing-strength '
        'improvement; external Nokamute performance; native PVS integration; real GPU OOM and physical reboot. '
        'No Nokamute moves or games entered replay.', '',
        'Run from the repository root after other heavy jobs finish:', '',
        '```powershell',
        'python -m genseki.rho.campaign --workspace Rho --resume --hours 8 --workers 2 --simulations 64 '
        '--replay-positions 200000 --max-plies 160 --train-positions 5000 --sample-positions 10000 '
        '--epochs 2 --batch-size 128 --arena-games 40 --device cuda',
        '```', '',
        'Source: genseki/rho/{core,campaign,status}.py. Workspace: champion/, challenger/, checkpoints/, '
        'replay/, reports/, models/, logs/, state.json and config.json. Shared engine sources and gitignore '
        'were unchanged; all Rho source, models and evidence remain visible to Git.', '',
        'Machine-readable full verification is in verification.json; per-generation training/arena evidence '
        'and every campaign are preserved alongside it.', '']
    atomic(root/'reports'/'IMPLEMENTATION.md', '\n'.join(lines).encode())
    print(json.dumps({'champion_sha256': model_hash, 'replay_positions': replay.size,
                      'tests_passed': result['tests_passed'], 'native_tests_passed': result['native_tests_passed'],
                      'workspace_bytes': result['workspace_bytes']}, indent=2))


if __name__ == '__main__':
    main()

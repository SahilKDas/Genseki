"""Read search targets from frozen Gen 1 without replacing its search implementation."""
import re
from genseki.uhp import UhpProcess
from train import response


def parse_diagnostics(diagnostics):
    iterations = re.findall(r'fullsearch depth (\d+) .*?value\s+([^;\s]+)', diagnostics)
    stats = re.search(r'Explored (\d+) nodes to depth (\d+)', diagnostics)
    if not iterations or not stats:
        raise RuntimeError('Gen 1 returned no completed-depth target; preserve diagnostics')
    completed, printed = iterations[-1]
    if int(completed) != int(stats[2]):
        raise RuntimeError('Gen 1 diagnostic depth disagreement')
    # Verbose Gen 1 deliberately collapses mate-distance values to infinity.
    # Preserve that fact rather than inventing an exact integer root score.
    terminal = printed in ('\u221e', '-\u221e')
    return dict(raw_score=None if terminal else int(printed), printed_score=printed,
                mate_range=terminal, completed_depth=int(completed), nodes=int(stats[1]))


class Gen1Teacher:
    def __init__(self, executable, log):
        self.log = log
        self.peer = UhpProcess([str(executable.resolve())], stderr=log)
        try:
            for option in ('NumThreads 1', 'TableSizeMiB 16',
                           'BackgroundPondering False', 'RandomOpening False', 'Verbose True'):
                response(self.peer, 'options set ' + option)
        except BaseException:
            self.peer.close()
            raise

    def search(self, game, depth=8, milliseconds=500):
        response(self.peer, 'newgame ' + game)
        self.log.seek(0, 2)
        offset = self.log.tell()
        move = response(self.peer, f'bestmove depthorseconds {depth} {milliseconds / 1000:.3f}')[0]
        self.log.seek(offset)
        diagnostics = self.log.read()
        parsed = parse_diagnostics(diagnostics)
        pv = response(self.peer, 'pv')
        return dict(parsed, move=move, orientation='side_to_move', pv=pv,
                    requested_depth=depth, milliseconds=milliseconds,
                    diagnostics=diagnostics)

    def close(self):
        self.peer.close()

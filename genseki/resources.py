"""Shared resource checks and cross-process exclusion for Python heavy jobs."""
from contextlib import contextmanager
import ctypes
import os
from pathlib import Path


HEAVY_PROCESS_PATTERNS = (
    'campaign', 'gauntlet', 'genseki.arena', 'gen2.py arena', 'gen2.py train',
    'gen2.py collect', 'gen2.py benchmark', 'gen2.py costs', 'gen2.py parity',
    'gen2.py schemas', 'gen2.py calibrate', 'gen2_lab.py', 'learning.py',
    'train.py', 'arena.py', 'benchmark.py', 'tournament', 'selfplay', 'training.py',
)


def available_ram():
    if os.name == 'nt':
        class Memory(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in
                ('total', 'available', 'page_total', 'page_available',
                 'virtual', 'virtual_available', 'extended')]
        memory = Memory()
        memory.length = ctypes.sizeof(memory)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            raise OSError('RAM watchdog unavailable')
        return memory.available
    return os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')


def heavy_job_path(root):
    return Path(root) / 'reports/work/heavy-job.lock'


def team_job_path(root):
    return Path(root) / '.tmp/team-genseki/heavy.lock'
@contextmanager
def job_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)

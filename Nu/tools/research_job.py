"""Standalone Nu controller exclusion; imported helpers inherit their caller's job."""
from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from genseki.resources import job_lock, heavy_job_path, team_job_path
_deadline=None

def check_deadline():
    if _deadline is not None and time.monotonic()>=_deadline:
        raise RuntimeError('research stage reached its two-hour limit')

@contextmanager
def research_job():
    global _deadline
    with job_lock(team_job_path(ROOT)), job_lock(heavy_job_path(ROOT)):
        if os.name=='nt':
            kernel=ctypes.windll.kernel32
            kernel.GetCurrentProcess.restype=ctypes.c_void_p
            kernel.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
            kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x40)
        _deadline=time.monotonic()+7200
        try:yield
        finally:_deadline=None

def run(main):
    if '--help' in sys.argv or '-h' in sys.argv:return main()
    with research_job():return main()

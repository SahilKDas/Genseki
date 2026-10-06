from __future__ import annotations
import json
import hashlib
import os
import sys
import time
import atexit
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
_last_storage_check = 0.
sys.path.insert(0, str(ROOT.parent))
from genseki.uhp import UhpProcess

def acquire_job():
    """One Iota heavy job, plus a read-only check for other project training jobs."""
    guard()
    if os.name=='nt':
        result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',
            "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' } | Select-Object ProcessId,CommandLine | ConvertTo-Json"],
            capture_output=True,text=True,timeout=15,check=True)
        processes=json.loads(result.stdout or '[]')
        if isinstance(processes,dict):processes=[processes]
        for proc in processes:
            text=(proc.get('CommandLine') or '').lower().replace('\\','/')
            if proc['ProcessId']!=os.getpid() and any(s in text for s in ('rho.campaign','gauntlet','tools/arena.py','tools/train.py','tools/match.py','tools/corpus.py','tools/bench.py','tools/supervision.py','gen2.py arena','gen2.py train')):
                raise RuntimeError('another heavy campaign/training/match process is active')
    lockpath=ROOT/'work/heavy.lock';lockpath.parent.mkdir(exist_ok=True)
    lock=lockpath.open('a+b');lock.seek(0)
    if lockpath.stat().st_size==0:lock.write(b'0');lock.flush();lock.seek(0)
    if os.name=='nt':
        import msvcrt
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    atexit.register(lock.close)
    return lock

def command(engine, text, timeout=5):
    lines, elapsed = engine.command(text, timeout)
    if not lines or lines[-1]!='ok':
        raise RuntimeError('missing UHP response terminator')
    if any(line.startswith(('err ', 'invalidmove ')) for line in lines):
        raise RuntimeError(lines)
    return lines[:-1], elapsed

def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temp.replace(path)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def guard():
    global _last_storage_check
    if os.name == 'nt':
        import ctypes
        class Memory(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)]+[
                (n, ctypes.c_ulonglong) for n in ('total', 'available', 'totalpage', 'availablepage', 'totalvirtual', 'availablevirtual', 'extended')]
        m = Memory(); m.length = ctypes.sizeof(m)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            raise RuntimeError('RAM measurement failed')
        if m.available < 512*1024**2:
            raise RuntimeError('RAM floor reached')
    now=time.monotonic()
    if now-_last_storage_check<2:return
    roots = [ROOT, ROOT.parent/'.tmp', ROOT.parent/'Nu/work', ROOT.parent/'Rho', ROOT.parent/'build', ROOT.parent/'build-nu', ROOT.parent/'Alpha/build']
    total = sum(p.stat().st_size for root in roots if root.exists() for p in root.rglob('*') if p.is_file())
    training = sum(p.stat().st_size for root in [ROOT/'work', ROOT.parent/'Nu/work', ROOT.parent/'Rho'] if root.exists() for p in root.rglob('*') if p.is_file())
    if total > 9_900_000_000 or training > 5_900_000_000:
        raise RuntimeError('temporary storage headroom exhausted')
    _last_storage_check=now

"""Small correctness suite with reproducible evidence, confined to Iota."""
import argparse
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from common import ROOT,atomic,digest


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'work/upgrade-v2/verification.json')
    args=p.parse_args();environment=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    temporary=ROOT/'work/test-tmp';temporary.mkdir(parents=True,exist_ok=True)
    environment.update(TEMP=str(temporary),TMP=str(temporary))
    sources=[path for directory in ('src','tools','tests') for path in (ROOT/directory).glob('*') if path.is_file()]
    report=dict(completed=False,python=sys.version,platform=platform.platform(),
                engine_sha256=digest(ROOT/'build/iota.exe'),sources={str(path.relative_to(ROOT)):digest(path) for path in sources},checks=[])
    for argv in (['ctest','--test-dir',str(ROOT/'build'),'--output-on-failure'],
                 [sys.executable,'-B','-m','unittest','discover','-s',str(ROOT/'tests'),'-p','test_*.py','-v']):
        start=time.monotonic()
        try:result=subprocess.run(argv,capture_output=True,text=True,env=environment,timeout=180)
        except subprocess.TimeoutExpired as error:
            def decoded(value):return value.decode(errors='replace') if isinstance(value,bytes) else value or ''
            report['checks'].append(dict(command=argv,returncode=None,seconds=time.monotonic()-start,
                                         error=repr(error),stdout=decoded(error.stdout),stderr=decoded(error.stderr)))
            atomic(args.output,report);raise
        report['checks'].append(dict(command=argv,returncode=result.returncode,seconds=time.monotonic()-start,
                                     stdout=result.stdout,stderr=result.stderr))
        atomic(args.output,report)
        if result.returncode:raise RuntimeError(f'verification failed: {argv}: {result.stdout} {result.stderr}')
    report['completed']=True;atomic(args.output,report)
    print(f'Correctness checks passed. Evidence: {args.output}')


if __name__=='__main__':main()

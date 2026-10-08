import subprocess
import sys
import tempfile
import struct
from pathlib import Path

p = subprocess.Popen([sys.argv[1]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
def read():
    result = []
    while True:
        line = p.stdout.readline()
        assert line, 'engine exited'
        line = line.rstrip('\n')
        if line == 'ok': return result
        result.append(line)
def command(text):
    p.stdin.write(text + '\n'); p.stdin.flush()
    return read()
try:
    assert read()[0].startswith('id Nu')
    assert command('newgame Base')[0].startswith('Base;')
    initial = command('nu-position')
    move = command('bestmove time 00:00:00.020')[0]
    assert move in command('validmoves')[0].split(';')
    assert not command('play ' + move)[0].startswith('err')
    played = command('nu-position')
    for malformed in ('1junk', '-1', '4294967296', '1 2'):
        assert command('undo ' + malformed)[0].startswith('err')
        assert command('nu-position') == played
    command('undo')
    assert command('nu-position') == initial
    assert command('options Threads 13')[0].startswith('err')
    assert command('bestmove time 00:00:00:1')[0].startswith('err')
    assert command('bestmove depth 1 junk')[0].startswith('err')
    assert command('options ThreatPlies 5')[0].startswith('err')
    assert command('options set ThreatPlies 1')[0].startswith('ThreatPlies;int;1')
    assert command('options set LateMoveReductions True')[0].startswith('LateMoveReductions;bool;True')
    assert command('options set LateMoveReductions False')[0].startswith('LateMoveReductions;bool;False')
    assert command('options get HybridEvaluation')==['HybridEvaluation;bool;False;False']
    assert command('options set HybridEvaluation True')==['HybridEvaluation;bool;True;False']
    assert command('options HybridWeight 201')[0].startswith('err')
    assert command('options HybridTerms 128')[0].startswith('err')
    assert command('options HybridTerms 0')==['HybridTerms;int;0;63;0;127']
    assert 'handcrafted 0 ' in command('nu-hybrid-eval')[0]
    assert command('options HybridTerms 63')==['HybridTerms;int;63;63;0;127']
    assert command('options HybridWeight 0')==['HybridWeight;int;0;100;0;200']
    assert 'enabled True' in command('nu-hybrid-eval')[0]
    assert command('options HybridWeight 100')==['HybridWeight;int;100;100;0;200']
    command('options HybridEvaluation False')
    assert command('nu-matchdraw')==['False']
    assert command('nu-moveid '+move)[0]
    assert command('play nonsense')[0].startswith('err')
    command('options set BackgroundPondering True')
    command('play ' + move)
    command('undo')
    assert command('nu-position') == initial
    command('options set BackgroundPondering False')
    command('newgame Base')
    before_features=command('nu-features')
    first=command('validmoves')[0].split(';')[0]
    game=command('play '+first)[0]
    lazy_features=command('nu-features')
    assert lazy_features!=before_features
    command('newgame '+game)
    assert command('nu-features')==lazy_features
finally:
    p.stdin.write('exit\n');p.stdin.flush();p.wait(timeout=5)
with tempfile.TemporaryDirectory() as directory:
    model = Path(directory) / 'broken.nnue'
    model.write_bytes(b'not a model' * 10)
    rejected = subprocess.run([sys.argv[1], '--model', str(model)], capture_output=True, timeout=5)
    assert rejected.returncode != 0
    payload=bytes(64*4+8192*64*2+64*2)
    checksum=14695981039346656037
    for byte in payload:checksum=((checksum^byte)*1099511628211)&((1<<64)-1)
    for schema in (1,2,3,4,5,6,7,8):
        model.write_bytes(struct.pack('<8sIIIIQ',b'NUNNUE1\0',schema,8192,64,256,checksum)+payload)
        loaded=subprocess.run([sys.argv[1],'--model',str(model)],input='nu-feature-schema\nnu-features\nexit\n',
                              text=True,capture_output=True,timeout=5)
        if schema==8:
            assert loaded.returncode!=0
        else:
            assert loaded.returncode==0,loaded.stderr
            assert f'\n{schema}\nok\n' in loaded.stdout
            if schema not in (5,7):assert '\nscore 0\n' in loaded.stdout

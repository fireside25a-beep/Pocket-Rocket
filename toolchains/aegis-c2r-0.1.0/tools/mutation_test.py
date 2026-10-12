#!/usr/bin/env python3
import hashlib, os, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BIN=ROOT/'build/bin/aegis-c2r'
BASE=(ROOT/'tests/positive/basic.c').read_bytes()

def run(src:bytes, d:Path, tag:str):
    inp=d/f'{tag}.c'; inp.write_bytes(src)
    rs=d/f'{tag}.rs'; ast=d/f'{tag}.ast'; js=d/f'{tag}.json'; pref=d/f'{tag}.cert'
    cp=subprocess.run([str(BIN),'translate',str(inp),'-o',str(rs),'--ast',str(ast),'--proof',str(js),'--aegis-prefix',str(pref)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    products=None
    if cp.returncode==0:
        products=tuple(hashlib.sha256((d/f'{tag}{s}').read_bytes()).hexdigest() for s in ('.rs','.ast','.json','.cert.dxl','.cert.dxs','.cert.dxasm'))
    return cp.returncode,cp.stdout,cp.stderr,products

spaces=[i for i,b in enumerate(BASE) if b==0x20][:11]
mutations=[]
for i,pos in enumerate(spaces):
    m=bytearray(BASE);m[pos]=0x09;mutations.append((f'a{i:03d}',bytes(m),True))
# 245 single-byte substitutions at the first #. Every replacement removes the
# only legal preprocessor introducer and therefore must be rejected.
pos=BASE.index(b'#')
vals=[v for v in range(256) if v!=ord('#')][:245]
for i,v in enumerate(vals):
    m=bytearray(BASE);m[pos]=v;mutations.append((f'r{i:03d}',bytes(m),False))
assert len(mutations)==256
accepted=rejected=0
with tempfile.TemporaryDirectory(prefix='aegis-c2r-mutate-') as td:
    d=Path(td)
    for tag,src,want_accept in mutations:
        r1=run(src,d,tag+'x'); r2=run(src,d,tag+'y')
        if r1[0]!=r2[0] or r1[1]!=r2[1] or r1[2]!=r2[2] or r1[3]!=r2[3]:
            print(f'FAIL nondeterministic mutation {tag}',file=sys.stderr);sys.exit(1)
        got=(r1[0]==0)
        if got!=want_accept:
            print(f'FAIL mutation class {tag}: got accept={got}',file=sys.stderr);sys.exit(1)
        accepted+=int(got);rejected+=int(not got)
print(f'MUTATION_PASS total=256 accepted={accepted} rejected={rejected}')

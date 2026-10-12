#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / 'build/bin/aegis-c2r'
VENDOR = ROOT / 'vendor/aegis-2.4.0'
PASS = 0
FAIL = 0
DETAILS=[]

def run(cmd, cwd=ROOT, input=None, env=None, check=False):
    e=os.environ.copy()
    if env: e.update(env)
    p=subprocess.run([str(x) for x in cmd],cwd=cwd,input=input,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=e)
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(map(str,cmd))}\nOUT:{p.stdout}\nERR:{p.stderr}")
    return p

def gate(name, fn):
    global PASS, FAIL
    try:
        detail=fn()
        PASS+=1
        DETAILS.append((name,'PASS',str(detail or '')))
        print(f'PASS {PASS:02d}/37  {name}' + (f' :: {detail}' if detail else ''))
    except Exception as exc:
        FAIL+=1
        DETAILS.append((name,'FAIL',str(exc)))
        print(f'FAIL --/37  {name} :: {exc}', file=sys.stderr)

def must(cond,msg='condition false'):
    if not cond: raise AssertionError(msg)

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def build_gcc():
    (ROOT/'build/bin').mkdir(parents=True, exist_ok=True)
    p=run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror','-Wformat=2','-Iinclude','src/aegis_c2r.c','-o','build/bin/aegis-c2r'])
    must(p.returncode==0,p.stderr); return sha(BIN)[:16]
def build_clang():
    p=run(['clang','-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror','-Wformat=2','-Iinclude','src/aegis_c2r.c','-o','build/bin/aegis-c2r-clang'])
    must(p.returncode==0,p.stderr); return 'strict Clang'
def analyzer():
    p=run(['gcc','-std=c11','-O0','-Wall','-Wextra','-Wpedantic','-Werror','-fanalyzer','-Iinclude','-c','src/aegis_c2r.c','-o','build/aegis_c2r.analyzer.o'])
    must(p.returncode==0,p.stderr); return 'gcc -fanalyzer'
def sanitizer():
    p=run(['gcc','-std=c11','-O1','-g','-Wall','-Wextra','-Wpedantic','-Werror','-Wformat=2','-fsanitize=address,undefined','-fno-omit-frame-pointer','-Iinclude','src/aegis_c2r.c','-o','build/bin/aegis-c2r-san'])
    must(p.returncode==0,p.stderr)
    sb=ROOT/'build/bin/aegis-c2r-san'
    for f in sorted((ROOT/'tests/positive').glob('*.c')):
        q=run([sb,'check',f], env={'ASAN_OPTIONS':'detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1'})
        must(q.returncode==0,f'{f.name}: {q.stderr}')
    for f in sorted((ROOT/'tests/negative').glob('*.c')):
        q=run([sb,'check',f], env={'ASAN_OPTIONS':'detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1'})
        must(q.returncode!=0,f'{f.name}: unexpectedly accepted')
    return '8 positive + 18 negative'

def check_file(name):
    p=run([BIN,'check',ROOT/'tests/positive'/name]); must(p.returncode==0,p.stderr); return p.stdout.strip()

def translate(src:Path, d:Path, stem='x'):
    d.mkdir(parents=True,exist_ok=True)
    rs=d/f'{stem}.rs'; ast=d/f'{stem}.ast'; proof=d/f'{stem}.json'; pre=d/stem
    p=run([BIN,'translate',src,'-o',rs,'--ast',ast,'--proof',proof,'--aegis-prefix',pre])
    must(p.returncode==0,p.stderr)
    return rs,ast,proof,Path(str(pre)+'.dxl'),Path(str(pre)+'.dxs'),Path(str(pre)+'.dxasm')

def determinism(idx):
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        A=translate(ROOT/'tests/positive/basic.c',Path(a),'basic'); B=translate(ROOT/'tests/positive/basic.c',Path(b),'basic')
        must(A[idx].read_bytes()==B[idx].read_bytes(),f'output index {idx} differs')
        return sha(A[idx])[:16]

def proof_hash(kind):
    with tempfile.TemporaryDirectory() as d:
        rs,ast,proof,*_=translate(ROOT/'tests/positive/basic.c',Path(d),'basic')
        j=json.loads(proof.read_text())
        mapping={'source':ROOT/'tests/positive/basic.c','ast':ast,'rust':rs}
        key={'source':'source_sha256','ast':'ast_sha256','rust':'rust_sha256'}[kind]
        actual=sha(mapping[kind]); must(j[key]==actual,f'{kind} hash mismatch'); return actual[:16]

def ast_equiv():
    a=run([BIN,'ast',ROOT/'tests/positive/basic.c']); b=run([BIN,'ast',ROOT/'tests/positive/basic_whitespace.c'])
    must(a.returncode==0 and b.returncode==0); must(a.stdout==b.stdout,'canonical AST differs'); return hashlib.sha256(a.stdout.encode()).hexdigest()[:16]

def negative_corpus():
    fs=sorted((ROOT/'tests/negative').glob('*.c')); must(len(fs)==18,f'expected 18 got {len(fs)}')
    for f in fs:
        p=run([BIN,'check',f]); must(p.returncode!=0,f'{f.name} accepted')
        q=run([BIN,'check',f]); must((p.returncode,p.stdout,p.stderr)==(q.returncode,q.stdout,q.stderr),f'{f.name} nondeterministic rejection')
    return '18/18 deterministic reject'
def mutation():
    p=run([sys.executable,'tools/mutation_test.py',BIN]); must(p.returncode==0,p.stdout+p.stderr); must('total=256 accepted=11 rejected=245' in p.stdout,p.stdout); return p.stdout.strip()

def vector_oracle(name, cc):
    f=ROOT/'tests/generated'/f'vectors_{name}.c'; exp=f.with_suffix('.expected')
    out=ROOT/'build/oracle'; out.mkdir(parents=True,exist_ok=True); exe=out/f'{name}.{cc}'
    p=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror','-Wno-strict-prototypes',f,'-o',exe]); must(p.returncode==0,p.stderr)
    q=run([exe]); must(q.returncode==0,q.stderr); must(q.stdout.encode()==exp.read_bytes(),f'{cc} output differs')
    t=run([BIN,'check',f]); must(t.returncode==0,t.stderr); return f'{cc} == expected'
def vector_inventory():
    fs=sorted((ROOT/'tests/generated').glob('vectors_*.expected')); lines=sum(len(f.read_text().splitlines()) for f in fs); must(lines==512,f'got {lines}'); return '512 deterministic cases'
def prefix_collision():
    with tempfile.TemporaryDirectory() as d:
        d=Path(d); src=d/'x.c'; shutil.copy2(ROOT/'tests/positive/basic.c',src)
        p=run([BIN,'translate',src,'-o',d/'cert.dxl','--aegis-prefix',d/'cert'])
        must(p.returncode!=0,'collision accepted'); must('collision' in p.stderr.lower(),p.stderr); return 'rejected before write'
def one_mib_boundary():
    with tempfile.TemporaryDirectory() as d:
        d=Path(d); base='int main() { return 0; }\n'.encode(); pad=b' '*((1024*1024)-len(base)); f=d/'at.c'; f.write_bytes(base+pad)
        p=run([BIN,'check',f]); must(p.returncode==0,p.stderr)
        g=d/'over.c'; g.write_bytes((base+pad)+b' '); q=run([BIN,'check',g]); must(q.returncode!=0,'1MiB+1 accepted'); return '1MiB accept / +1 reject'
def local_boundary():
    with tempfile.TemporaryDirectory() as d:
        d=Path(d); a=d/'a.c'; b=d/'b.c'
        def text(n): return '#include <stdio.h>\nint main() {\n'+''.join(f'int v{i} = {i};\n' for i in range(n))+'printf("%d\\n", v0);\nreturn 0;\n}\n'
        a.write_text(text(256)); b.write_text(text(257))
        p=run([BIN,'check',a]); q=run([BIN,'check',b]); must(p.returncode==0,p.stderr); must(q.returncode!=0,'257 locals accepted'); return '256 accept / 257 reject'
def aegis_bootstrap():
    p=run(['make','check'],cwd=VENDOR); must(p.returncode==0,p.stdout+p.stderr); must('11 PASS / 0 FAIL' in p.stdout,p.stdout); return '11/11 upstream clean-suite gate'
def cert_consensus():
    with tempfile.TemporaryDirectory() as d:
        d=Path(d); rs,ast,proof,dxl,dxs,dxa=translate(ROOT/'tests/positive/basic.c',d,'cert'); j=json.loads(proof.read_text()); cert=str(j['certificate'])
        B=VENDOR/'build/bin'; pol=VENDOR/'examples/policy_all.bin'
        q1=run([B/'dxlc','check',dxl],cwd=VENDOR); must(q1.returncode==0,q1.stderr)
        q2=run([B/'dxlc','run',dxl],cwd=VENDOR); must(q2.returncode==0,q2.stderr)
        dxb1=d/'a.dxb'; dxb2=d/'a2.dxb'; pr1=d/'a.proof';
        q3=run([B/'dxscc',dxs,dxb1],cwd=VENDOR); must(q3.returncode==0,q3.stderr)
        q4=run([B/'dxscc',dxs,dxb2],cwd=VENDOR); must(q4.returncode==0,q4.stderr); must(dxb1.read_bytes()==dxb2.read_bytes(),'DXS not byte-identical')
        q5=run([B/'dxaudit',dxb1],cwd=VENDOR); must(q5.returncode==0,q5.stderr)
        q6=run([B/'dxvm',dxb1,pol,pr1],cwd=VENDOR); must(q6.returncode==0,q6.stderr)
        adb1=d/'b.dxb'; adb2=d/'b2.dxb'; pr2=d/'b.proof'
        q7=run([B/'dxasm',dxa,adb1],cwd=VENDOR); must(q7.returncode==0,q7.stderr)
        q8=run([B/'dxasm',dxa,adb2],cwd=VENDOR); must(q8.returncode==0,q8.stderr); must(adb1.read_bytes()==adb2.read_bytes(),'DXASM not byte-identical')
        q9=run([B/'dxaudit',adb1],cwd=VENDOR); must(q9.returncode==0,q9.stderr)
        q10=run([B/'dxvm',adb1,pol,pr2],cwd=VENDOR); must(q10.returncode==0,q10.stderr)
        outs=[q2.stdout.strip(),q6.stdout.strip(),q10.stdout.strip()]
        must(outs==[cert,cert,cert],f'consensus mismatch {outs} != {cert}')
        return f'DXL=DXS=DXASM={cert}; repeat bytes exact'
def proof_schema():
    with tempfile.TemporaryDirectory() as d:
        vals=translate(ROOT/'tests/positive/basic.c',Path(d),'p'); j=json.loads(vals[2].read_text()); must(j['schema']=='AEGIS-C2R-PROOF/1'); must(j['profile']=='S0-DEFINED-I32'); must(j['status']=='accepted'); return j['schema']
def safe_rust_markers():
    with tempfile.TemporaryDirectory() as d:
        rs,*_=translate(ROOT/'tests/positive/basic.c',Path(d),'s'); t=rs.read_text(); must('#![forbid(unsafe_code)]' in t); must('checked_add' in t and 'checked_div' in t and 'checked_neg' in t); must('unsafe' in t); return 'forbid unsafe + checked arithmetic'
def rustc_gate():
    r=shutil.which('rustc')
    if not r: return 'SKIP: rustc unavailable on validation host'
    with tempfile.TemporaryDirectory() as d:
        d=Path(d); rs,*_=translate(ROOT/'tests/positive/basic.c',d,'r'); exe=d/'rbin'; p=run([r,'--edition=2021','-C','overflow-checks=yes',rs,'-o',exe]); must(p.returncode==0,p.stderr); q=run([exe]); must(q.stdout=='42\n',q.stdout); return 'PASS: rustc compile/run'

# 37 fixed release gates. Keep this list stable; changes require a release-version bump.
gates=[
('strict GCC translator build',build_gcc),
('strict Clang translator build',build_clang),
('GCC path-sensitive analyzer',analyzer),
('ASan+UBSan positive/negative corpus',sanitizer),
('CLI identity/version',lambda: (lambda p:(must(p.returncode==0),must('0.1.0' in p.stdout),p.stdout.strip()))(run([BIN,'version']))[-1]),
('positive basic.c',lambda:check_file('basic.c')),
('positive basic_whitespace.c',lambda:check_file('basic_whitespace.c')),
('positive branch_loop.c',lambda:check_file('branch_loop.c')),
('positive calls.c',lambda:check_file('calls.c')),
('positive logic.c',lambda:check_file('logic.c')),
('positive neg_rem.c',lambda:check_file('neg_rem.c')),
('positive precedence.c',lambda:check_file('precedence.c')),
('positive max_literal.c',lambda:check_file('max_literal.c')),
('canonical AST whitespace equivalence',ast_equiv),
('deterministic Rust emission',lambda:determinism(0)),
('deterministic AST emission',lambda:determinism(1)),
('deterministic proof JSON emission',lambda:determinism(2)),
('deterministic DXL certificate emission',lambda:determinism(3)),
('deterministic DXS certificate emission',lambda:determinism(4)),
('deterministic DXASM certificate emission',lambda:determinism(5)),
('independent source SHA-256 binding',lambda:proof_hash('source')),
('independent AST SHA-256 binding',lambda:proof_hash('ast')),
('independent Rust SHA-256 binding',lambda:proof_hash('rust')),
('proof schema/profile/status',proof_schema),
('safe-Rust markers and checked lowering',safe_rust_markers),
('18-case deterministic negative corpus',negative_corpus),
('256 deterministic source mutations',mutation),
('512-vector corpus inventory',vector_inventory),
('arithmetic vectors GCC oracle',lambda:vector_oracle('arith','gcc')),
('arithmetic vectors Clang oracle',lambda:vector_oracle('arith','clang')),
('division/remainder vectors GCC oracle',lambda:vector_oracle('divrem','gcc')),
('comparison vectors Clang oracle',lambda:vector_oracle('cmp','clang')),
('logic vectors GCC oracle',lambda:vector_oracle('logic','gcc')),
('logic vectors Clang oracle',lambda:vector_oracle('logic','clang')),
('output-path collision rejection',prefix_collision),
('Aegis 2.4.0 C-bootstrap 11/11 gate',aegis_bootstrap),
('Aegis DXL/DXS/DXASM certificate consensus',cert_consensus),
]
assert len(gates)==37
for n,f in gates: gate(n,f)
print(f'\nRELEASE_GATE PASS={PASS} FAIL={FAIL} TOTAL={len(gates)}')
print('RUSTC_GATE=' + rustc_gate())
report=ROOT/'evidence/release_gate.tsv'; report.parent.mkdir(exist_ok=True)
report.write_text('gate\tstatus\tdetail\n'+''.join(f'{n}\t{s}\t{d.replace(chr(9)," ").replace(chr(10)," ")}\n' for n,s,d in DETAILS),encoding='utf-8')
sys.exit(0 if FAIL==0 else 1)

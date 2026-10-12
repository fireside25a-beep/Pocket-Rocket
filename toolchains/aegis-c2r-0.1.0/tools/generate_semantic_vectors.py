#!/usr/bin/env python3
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tests' / 'generated'
OUT.mkdir(parents=True, exist_ok=True)

def cdiv(a,b):
    assert b != 0
    return abs(a)//abs(b) * (-1 if (a<0)^(b<0) else 1)
def crem(a,b): return a - cdiv(a,b)*b

def write(name, exprs):
    c = ['#include <stdio.h>', 'int main() {']
    expected=[]
    for expr,val in exprs:
        c.append(f'    printf("%d\\n", {expr});')
        expected.append(str(val))
    c.append('    return 0;')
    c.append('}')
    (OUT/f'{name}.c').write_text('\n'.join(c)+'\n', encoding='ascii')
    (OUT/f'{name}.expected').write_text('\n'.join(expected)+'\n', encoding='ascii')

arith=[]
for i in range(128):
    a=(i*37)%401-200; b=(i*19)%41-20; c=(i*7)%21-10
    val=a+b*c
    arith.append((f'{a} + {b} * {c}', val))
write('vectors_arith', arith)

divr=[]
for i in range(128):
    a=(i*97)%2001-1000; b=(i*13)%31-15
    if b==0: b=7
    if i%2==0: expr=f'{a} / {b}'; val=cdiv(a,b)
    else: expr=f'{a} % {b}'; val=crem(a,b)
    divr.append((expr,val))
write('vectors_divrem', divr)

cmpv=[]
ops=[('<',lambda a,b:a<b),('<=',lambda a,b:a<=b),('>',lambda a,b:a>b),('>=',lambda a,b:a>=b),('==',lambda a,b:a==b),('!=',lambda a,b:a!=b)]
for i in range(128):
    a=(i*11)%71-35; b=(i*17)%71-35; op,fn=ops[i%len(ops)]
    cmpv.append((f'{a} {op} {b}', int(fn(a,b))))
write('vectors_cmp', cmpv)

# Logic vectors intentionally use initialized variables rather than constant-only
# operands so GCC/Clang can compile the oracle corpus under -Werror without
# constant-logical-operand diagnostics. This also exercises the exact 256-local
# S0 profile boundary (128 pairs).
c = ['#include <stdio.h>', 'int main() {']
expected=[]
vals=[]
for i in range(128):
    a=(i*5)%9-4; b=(i*7)%11-5
    vals.append((a,b))
    c.append(f'    int a{i} = {a};')
    c.append(f'    int b{i} = {b};')
for i,(a,b) in enumerate(vals):
    mode=i%4
    if mode==0: expr=f'(!a{i}) + (b{i} - b{i})'; val=int(not a)
    elif mode==1: expr=f'a{i} && b{i}'; val=int(bool(a) and bool(b))
    elif mode==2: expr=f'a{i} || b{i}'; val=int(bool(a) or bool(b))
    else: expr=f'(a{i} < b{i}) || (a{i} == b{i})'; val=int((a<b) or (a==b))
    c.append(f'    printf("%d\\n", {expr});')
    expected.append(str(val))
c.append('    return 0;')
c.append('}')
(OUT/'vectors_logic.c').write_text('\n'.join(c)+'\n', encoding='ascii')
(OUT/'vectors_logic.expected').write_text('\n'.join(expected)+'\n', encoding='ascii')
print('generated 512 semantic vectors')

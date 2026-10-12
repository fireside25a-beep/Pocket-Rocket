#!/usr/bin/env python3
"""Create a sorted, fixed-metadata ZIP for reproducible Aegis-C2R releases."""
from pathlib import Path
import os, stat, sys, zipfile
FIXED=(2026,8,24,0,0,0)
if len(sys.argv)!=4:
    raise SystemExit('usage: deterministic_zip.py ROOT PREFIX OUTPUT.zip')
root=Path(sys.argv[1]).resolve(); prefix=sys.argv[2].strip('/'); out=Path(sys.argv[3])
paths=[]
for p in root.rglob('*'):
    if p.is_symlink(): raise SystemExit(f'symlink forbidden: {p}')
    if p.is_file(): paths.append(p)
paths.sort(key=lambda p:p.relative_to(root).as_posix())
out.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9,strict_timestamps=True) as z:
    for p in paths:
        rel=p.relative_to(root).as_posix(); arc=f'{prefix}/{rel}' if prefix else rel
        data=p.read_bytes(); mode=0o755 if os.access(p,os.X_OK) else 0o644
        zi=zipfile.ZipInfo(arc,FIXED); zi.create_system=3; zi.compress_type=zipfile.ZIP_DEFLATED
        zi.external_attr=(stat.S_IFREG|mode)<<16; zi.flag_bits|=0x800
        z.writestr(zi,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
print(out)

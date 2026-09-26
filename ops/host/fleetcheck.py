import sys; sys.path.insert(0,'/home/alan/Documents/repos/chimera-miner/ops')
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from ssh_reliable import ssh_checked
from cell_ops import load_map
m=load_map(); cells=m['cells']
MIN=sorted([c for c,v in cells.items() if v.get('miner')=='mining'], key=int)
def probe(c):
    cell=cells[c]; home=Path(f"/home/alan/Documents/railways/sessions/session-{cell.get('railway_session')}")
    log=cell.get('log') or f'daemon_r{c}.log'
    ok,out=ssh_checked(home, cell['service'],
        f'echo MARK-END; tail -12 /data/work/{log} 2>/dev/null', 'MARK-END', timeout=170, tries=2)
    o=out or ''
    st='ALIVE' if ('Worker alive' in o and 'Preview healthy' in o) else ('CYCLING' if 'tab_fail_streak' in o else ('IDLE' if ok else 'SSH-FAIL'))
    return c,st
with ThreadPoolExecutor(max_workers=2) as ex:
    res=list(ex.map(probe,MIN))
for c,s in res: print(f'cell-{c}: {s}', flush=True)
print('ALIVE:', sum(1 for _,s in res if s=='ALIVE'), '/', len(res))

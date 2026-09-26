import sys; sys.path.insert(0,'/home/alan/Documents/repos/chimera-miner/ops')
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from ssh_reliable import ssh_checked
from cell_ops import load_map
m=load_map(); cells=m['cells']
MIN=sorted([c for c,v in cells.items() if v.get('miner')=='mining'], key=int)
def probe(c):
    cell=cells[c]; home=Path(f"/home/alan/Documents/railways/sessions/session-{cell.get('railway_session')}")
    ok,out=ssh_checked(home, cell['service'],
      'echo MARK-END; '
      'echo "mem=$(( $(cat /sys/fs/cgroup/memory.current) / 1048576 ))MB/$(( $(cat /sys/fs/cgroup/memory.max) / 1048576 ))MB"; '
      'grep -E "^(oom_kill|max)" /sys/fs/cgroup/memory.events | tr "\\n" " "; echo; '
      'echo "chrome=$(pgrep -c chrome) big=$(for p in $(pgrep chrome|head -8); do awk "/VmRSS/{print \\$2}" /proc/$p/status 2>/dev/null; done | sort -n | tail -1)kB"', 'MARK-END', timeout=175, tries=2)
    return c,(out or '')
with ThreadPoolExecutor(max_workers=2) as ex:
    for c,o in ex.map(probe,MIN):
        line=' | '.join(x.strip() for x in (o or '').split('\n') if x.strip() and 'MARK-END' not in x)
        print(f'cell-{c}: {line[:150]}', flush=True)

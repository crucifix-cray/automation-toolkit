import sys; sys.path.insert(0,'/home/alan/Documents/repos/chimera-miner/ops')
from pathlib import Path
from ssh_reliable import ssh_checked
from cell_ops import load_map
m=load_map(); cells=m['cells']
for c in ('13','35'):
    cell=cells[c]; home=Path(f"/home/alan/Documents/railways/sessions/session-{cell.get('railway_session')}")
    script=('echo MARK-END; '
      'awk \'/^anon /{a=$2} /^file /{f=$2} /^shmem /{sh=$2} END{printf "anon=%.0fMB file=%.0fMB shmem=%.0fMB\\n", a/1048576, f/1048576, sh/1048576}\' /sys/fs/cgroup/memory.stat; '
      'echo "top-rss:"; ps -eo rss,comm --sort=-rss | head -5 | sed "s/^/  /"; '
      'echo "vol:"; du -sh /data 2>/dev/null | sed "s/^/  /"; '
      'echo "swap:"; free -m | sed -n 3p | sed "s/^/  /"')
    ok,out=ssh_checked(home, cell['service'], script, 'MARK-END', timeout=200, tries=2)
    print(f'===== cell-{c}'); print((out or '')[-600:])

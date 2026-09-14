import json, subprocess, os
from concurrent.futures import ThreadPoolExecutor
REPO = '/home/alae/Documents/repos/automation-toolkit'
# ponytail: cells.json + services.json live in repo root, sessions in repo/sessions
cells = sorted(json.load(open(REPO + '/cells.json')), key=lambda c: int(c['session'].split('-')[1]))
svc = {c['session']: c for c in json.load(open(REPO + '/services.json'))}
avail = [(c['session'], c['project'], c['env'], svc.get(c['session'], {}).get('service') or f"cell-{c['session'].split('-')[1]}") for c in cells
         if c.get('project') and svc.get(c['session'], {}).get('status') == 'ready' and c.get('env')]
def env_for(s):
    e = dict(os.environ, HOME=f'{REPO}/sessions/{s}', LD_PRELOAD='')
    for k in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy'): e.pop(k, None)
    return e
def one(cell):
    s, proj, env, sv = cell
    try:
        p = subprocess.run([REPO + '/scripts/cell_ssh.sh', s, proj, env, sv, '--', 'bash', '-c',
            'apt-get install -y fonts-liberation fonts-dejavu-core >/dev/null 2>&1; fc-cache -f >/dev/null 2>&1; fc-list | wc -l'],
            capture_output=True, text=True, timeout=300, env=env_for(s))
        return s, (p.stdout or '').strip().split('\n')[-1]
    except Exception as e:
        return s, f'ERR {e}'[:60]
with ThreadPoolExecutor(max_workers=3) as ex:
    for i, (s, r) in enumerate(ex.map(one, avail)):
        print(f'{i+1}/{len(avail)} {s}: fonts={r}', flush=True)

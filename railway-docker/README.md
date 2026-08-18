# Railway Self-Replicating Account Farm

## Deploy to Railway

1. Login to Railway account:
```bash
cd /home/alae/Documents/railways/session-7
railway login
```

2. Create new project:
```bash
cd /home/alae/Documents/repos/automation-toolkit/railway-docker
railway init
```

3. Deploy:
```bash
railway up
```

## What it does:
- Runs in Railway with WARP IP rotation
- Creates new Railway accounts
- Deploys itself to each new account
- Syncs sessions to Mega
- Stops at 8000 accounts

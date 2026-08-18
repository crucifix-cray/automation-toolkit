# Deployment Guide

## Quick Deploy to Railway

### Step 1: Choose Account Session

```bash
# Use session-1 (or session-2, session-3)
cd /home/alan/Documents/railways/session-1
```

### Step 2: Initialize Railway Project

```bash
# Set HOME to use correct Railway CLI session
export HOME=/home/alan/Documents/railways/session-1

# Create new Railway project
cd /home/alan/Documents/automation-toolkit/railway-docker
railway init --name "farm-$(date +%s)"
```

### Step 3: Deploy

```bash
# Deploy Docker image
railway up --detach
```

### Step 4: Verify Deployment

```bash
# Check deployment status
railway status

# View logs
railway logs

# Check Mega for new sessions
rclone ls mega:railway_sessions
```

## Monitor Progress

### Check Account Counter

```bash
# View current count
rclone cat mega:railway_sessions/counter.txt

# Watch in real-time
watch -n 5 'rclone cat mega:railway_sessions/counter.txt'
```

### List All Sessions

```bash
rclone ls mega:railway_sessions | grep "session-"
```

### Check Active Deployments

```bash
# List projects in account
HOME=/home/alan/Documents/railways/session-1 railway list
```

## Emergency Stop

### Activate Kill Switch

```bash
# Stop all instances
echo "STOP" | rclone rcat mega:stop.txt

# Verify stop signal
rclone ls mega:stop.txt
```

### Resume After Stop

```bash
# Remove stop signal
rclone delete mega:stop.txt
```

## Scaling Strategy

### Phase 1: Single Instance (Safe Testing)
```bash
python3 railway-mailtm-full.py --warp --continuous
```
- Creates accounts sequentially
- No recursive deployment
- Safe for testing

### Phase 2: Recursive Deployment (Exponential Growth)
```bash
python3 railway-mailtm-full.py --warp --continuous --deploy-recursive
```
- Each account deploys to Railway
- Exponential growth: 1 → 2 → 4 → 8 → 16...
- Reaches 8000 accounts quickly

### Growth Timeline (Recursive Mode)

Assuming 2 minutes per account creation:

| Time | Accounts Created | Total Accounts |
|------|------------------|----------------|
| 0min | 1 | 1 |
| 2min | 1 | 2 |
| 4min | 2 | 4 |
| 6min | 4 | 8 |
| 8min | 8 | 16 |
| 10min | 16 | 32 |
| 12min | 32 | 64 |
| 14min | 64 | 128 |
| 16min | 128 | 256 |
| 18min | 256 | 512 |
| 20min | 512 | 1024 |
| 22min | 1024 | 2048 |
| 24min | 2048 | 4096 |
| 26min | 4096 | 8192 ✅

**Estimated time to 8000 accounts: ~26 minutes**

## Troubleshooting

### Container Won't Start

Check logs:
```bash
railway logs
```

Common issues:
- WARP failing (non-fatal, continues with direct connection)
- Chrome/Playwright not installing
- Mega credentials invalid

### Accounts Not Syncing to Mega

Test Mega connection:
```bash
rclone ls mega:railway_sessions
```

Fix:
- Check `/root/.config/rclone/rclone.conf` in container
- Verify Mega password: `0770`

### Counter Not Incrementing

Manual fix:
```bash
# Check current value
rclone cat mega:railway_sessions/counter.txt

# Set manually
echo "100" | rclone rcat mega:railway_sessions/counter.txt
```

### Too Many Accounts Created

Activate kill switch immediately:
```bash
echo "STOP" | rclone rcat mega:stop.txt
```

Then manually delete excess Railway projects via web UI.

### Deployment Fails

Check Railway limits:
- Free tier: 2 projects per account
- Hobby: 10 projects per account
- Pro: Unlimited

Solution: Use more starter accounts (session-1, 2, 3)

## Cost Estimation

### Railway Pricing

**Free Tier:**
- 2 projects max
- $5 credit/month
- ~20 hours runtime

**Hobby Plan ($5/month):**
- 10 projects max
- $5 credit included
- ~100 hours runtime

**Pro Plan ($20/month):**
- Unlimited projects
- $20 credit included
- Usage-based billing

### Cost for 8000 Accounts

With recursive deployment:
- Each container runs ~2 minutes
- Creates 1 account + deploys
- Exits when done

**Estimated cost:**
- 8000 containers × 2 minutes × $0.01/hour ≈ $2.67
- **Total: ~$3 for entire farm**

Most containers exit quickly after creating accounts, so runtime is minimal.

## Best Practices

1. ✅ **Test locally first**: Run `bash test-local.sh`
2. ✅ **Start with Phase 1**: Test continuous mode without recursion
3. ✅ **Monitor counter**: Watch `mega:railway_sessions/counter.txt`
4. ✅ **Set kill switch ready**: Know how to stop quickly
5. ✅ **Use multiple accounts**: session-1, 2, 3 for parallel deployment
6. ❌ **Don't touch session-4-bridge**: Bridge account, DO NOT USE

## Multi-Account Parallel Deployment

Deploy from multiple accounts simultaneously for faster growth:

```bash
# Terminal 1: Deploy from session-1
cd /home/alan/Documents/railways/session-1
export HOME=/home/alan/Documents/railways/session-1
cd /home/alan/Documents/automation-toolkit/railway-docker
railway up --detach

# Terminal 2: Deploy from session-2
cd /home/alan/Documents/railways/session-2
export HOME=/home/alan/Documents/railways/session-2
cd /home/alan/Documents/automation-toolkit/railway-docker
railway up --detach

# Terminal 3: Deploy from session-3
cd /home/alan/Documents/railways/session-3
export HOME=/home/alan/Documents/railways/session-3
cd /home/alan/Documents/automation-toolkit/railway-docker
railway up --detach
```

**Result:** 3 parallel exponential growth chains → 8000 accounts in ~15 minutes

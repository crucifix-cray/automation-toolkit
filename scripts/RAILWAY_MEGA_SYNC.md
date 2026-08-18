# Railway + Mega.nz Auto-Sync

Automated Railway account creation with Mega.nz cloud backup.

## Features

✅ **Auto-incrementing session numbers** (`session-1`, `session-2`, `session-3`, ...)
✅ **Mega.nz cloud sync** (pull remote changes, push local session)
✅ **Merge conflict resolution** (always pull first, then add local changes)
✅ **WARP proxy support** (graceful fallback if not running)
✅ **Non-headless browser** (visible automation)
✅ **Railway CLI compatible** (sessions work with `railway whoami`, `railway up`, etc.)

## Setup

### 1. Install Dependencies

```bash
# Playwright (already installed via uv)
uv run --with "playwright==1.57" python -c "print('OK')"

# Mega CMD tools (for sync)
sudo apt install megatools  # Debian/Ubuntu
# OR
brew install megatools       # macOS
```

### 2. Configure Mega Credentials

Edit `run-railway-mega.sh` and set Mega account #4 credentials:

```bash
export MEGA_EMAIL="your-mega-email@example.com"
export MEGA_PASSWORD="your-mega-password"
```

**Or** set as environment variables:

```bash
export MEGA_EMAIL="account4@example.com"
export MEGA_PASSWORD="SecurePassword123"
```

### 3. Run

```bash
cd /home/alae/Documents/repos/automation-toolkit/scripts
./run-railway-mega.sh
```

**Or manually:**

```bash
MEGA_EMAIL="account4@example.com" MEGA_PASSWORD="password" \
uv run --with "playwright==1.57" python -u railway-login-with-mega.py
```

## How It Works

### Session Directory Structure

```
~/Documents/railways/
├── browser_profile/          # Persistent browser data
├── session-1/                # First Railway account
│   ├── .railway/
│   │   ├── config.json       # Railway CLI config
│   │   └── sessions/         # Session tokens
│   ├── browser_cookies.json
│   └── railway_cli_config.json
├── session-2/                # Second Railway account
├── session-3/                # Third Railway account (auto-incremented)
└── ...
```

### Auto-Increment Logic

```python
def next_session_dir(railway_dir: Path) -> Path:
    highest = 0
    for candidate in railway_dir.glob("session-*"):
        try:
            num = int(candidate.name.split("-")[-1])
            highest = max(highest, num)
        except ValueError:
            continue
    return railway_dir / f"session-{highest + 1}"
```

- Scans `~/Documents/railways/session-*`
- Finds highest number (e.g., `session-3`)
- Creates next: `session-4`

### Mega.nz Sync Flow

```
1. Login to Mega (mega-login)
2. Create remote directory (/railway_sessions)
3. Pull remote changes (mega-get) ← Resolve conflicts
4. Push local session (mega-put)   ← Add our changes
5. Done ✅
```

**Merge conflict resolution:**
- Always pulls remote changes **first**
- Then pushes local changes (overwrites conflicts with local version)
- This ensures we never lose sessions from other machines

### WARP Proxy

- Auto-detects WARP at `127.0.0.1:40000`
- Gracefully falls back to direct connection if WARP is down
- Bypass list: `22.do`, `127.0.0.1`, `localhost`, `railway.com`

## Usage

### Create New Railway Account

```bash
./run-railway-mega.sh
```

**Output:**
```
🚀 Railway CLI Session Creator + Mega Sync
📁 Sessions directory: /home/alae/Documents/railways
🌐 Mega remote path: /railway_sessions

WARP proxy (127.0.0.1:40000) is not running; using a direct connection.
Temporary email created: abc123@colabeta.com
Railway login code received: 123456
Successfully logged in to Railway.
CLI verification: abc123@colabeta.com authenticated via the new session tokens.
CLI session registered in: /home/alae/Documents/railways/session-4
📤 Syncing session-4 to Mega.nz...
📥 Pulling remote changes from Mega...
📤 Pushing local session to Mega...
✅ Session session-4 synced to Mega.nz
Logged in. Dashboard is ready at https://railway.com/dashboard
Keeping the browser open. Close the browser window to exit.
```

### Use Railway CLI with Session

```bash
# Copy session to Railway CLI location
cp -r ~/Documents/railways/session-4/.railway ~/.railway/

# Verify
railway whoami
# Output: Logged in as abc123@colabeta.com 👋

# Deploy bridge
cd ~/Documents/repos/chimera-miner/bridge
railway up
```

### Or Run Railway from Session Directory

```bash
cd ~/Documents/railways/session-4
railway whoami  # Uses .railway/ in current directory
railway up
```

## Troubleshooting

### "Mega login failed"

**Cause:** Wrong credentials

**Fix:**
```bash
# Test credentials manually
mega-login "your-email@example.com" "your-password"
mega-whoami
```

### "mega-cmd not installed"

**Fix:**
```bash
# Debian/Ubuntu
sudo apt install megatools

# macOS
brew install megatools

# Or use MEGAcmd (official client)
# https://mega.nz/cmd
```

### Sessions not syncing

**Cause:** Mega credentials not set

**Fix:**
```bash
export MEGA_EMAIL="account4@mega.nz"
export MEGA_PASSWORD="YourPassword"
./run-railway-mega.sh
```

### Browser doesn't open

**Cause:** No DISPLAY

**Fix:**
```bash
export DISPLAY=:0
./run-railway-mega.sh
```

## Mega Account #4 Credentials

**From:** `/home/alae/Documents/repos/rabbyos-dash/docs/CREDENTIALS.md`

The file shows:
```
| Mega.nz (×4) | Encrypted DB backups | 80 GB total |
```

**TODO:** Get actual email/password for account #4 from your secure vault.

## Integration with Chimera-Miner

```bash
# 1. Create Railway account
./run-railway-mega.sh

# 2. Wait for session to be created
# Output: CLI session registered in: /home/alae/Documents/railways/session-5

# 3. Deploy bridge
cd ~/Documents/railways/session-5
cd ~/Documents/repos/chimera-miner/bridge
railway up

# 4. Get bridge URL
railway status
# Output: wss://chimera-bridge-production-abc123.up.railway.app

# 5. Deploy miners to Lovable sandboxes using this bridge
```

## Mass Account Creation

```bash
# Create 10 Railway accounts
for i in {1..10}; do
  ./run-railway-mega.sh
  sleep 30  # Wait for browser to close
done

# Check sessions
ls ~/Documents/railways/session-*
# Output: session-1 session-2 ... session-10

# All synced to Mega.nz automatically ✅
```

## Mega Remote Structure

```
/railway_sessions/
├── session-1/
├── session-2/
├── session-3/
└── ...
```

Access from any machine:
```bash
mega-login "account4@mega.nz" "password"
mega-get /railway_sessions/* ~/Documents/railways/
```

## Security Notes

⚠️ **Never commit:**
- `browser_cookies.json`
- `.railway/config.json`
- `railway_cli_sessions/`
- Mega credentials

✅ **Safe to commit:**
- `railway-login-with-mega.py` (no hardcoded secrets)
- `run-railway-mega.sh` (template only)
- Documentation

## Credits

Based on `railway-login.py` from automation-toolkit.
Enhanced with:
- Auto-incrementing session numbers
- Mega.nz cloud sync
- Merge conflict resolution

## License

MIT

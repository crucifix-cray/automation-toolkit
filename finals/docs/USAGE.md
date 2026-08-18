# Usage Guide - lov-api.py

## Basic Usage

### Run Script

```bash
cd /home/alan/Documents/automation-toolkit/finals
python3 lov-api.py
```

### Expected Output

```
WARP proxy (127.0.0.1:40000) is not running; using direct connection.
🌐 Browser egress IP: fl=40f370...

🔄 Attempt 1/3: Creating account via TRUE API-ONLY mode...
📋 Loaded 4 used emails
🔄 Attempt 1/30: Creating email via API...
  📧 Created: test123@gmail.com (ID: 42)
  ✅ Valid Gmail format
  🔍 Testing mailbox via API...
  ✅ Mailbox working!
🎉 FOUND WORKING GMAIL: test123@gmail.com (ID: 42)

📝 Lovable: No account found, creating one...
  📥 Check #1: Polling API for emails...
✅ Found Lovable reset link!

💾 Saved test123@gmail.com to used list
✅ Saved 46 cookies to sessions/session-8/cookies.json
✅ Saved session config to sessions/session-8/config.json

============================================================
🎉 SUCCESS!
============================================================
{
  "verified": true,
  "email": "test123@gmail.com",
  "password": "test123@gmail.com1",
  "dashboard_url": "https://lovable.dev/dashboard",
  "session_dir": "sessions/session-8",
  "session_number": 8
}

✋ Browser staying open. Press Enter to close...
```

## Command-Line Options

### Connect to Existing Browser

```bash
# Start Chrome with debugging
google-chrome --remote-debugging-port=9222 &

# Get CDP URL
cdp_url=$(curl -s localhost:9222/json | jq -r '.[0].webSocketDebuggerUrl')

# Run script with CDP
python3 lov-api.py --cdp-url "$cdp_url"
```

### Environment Variables

```bash
# Keep browser open (default: 1)
KEEP_BROWSER_OPEN=0 python3 lov-api.py

# Use CDP from environment
export BU_CDP_WS="ws://localhost:9222/devtools/browser/..."
python3 lov-api.py
```

## Use Cases

### 1. Single Account Creation

```bash
# Create one account
python3 lov-api.py

# Output saved to:
# - sessions/session-N/cookies.json
# - sessions/session-N/config.json
# - /home/alan/Documents/used-tempmailhub-emails.txt
```

### 2. Multiple Accounts

```bash
# Create 5 accounts in sequence
for i in {1..5}; do
    echo "Creating account $i/5..."
    python3 lov-api.py
    sleep 10  # Wait between runs to avoid rate limiting
done

# Check results
ls -la sessions/
```

### 3. Load Existing Session

```python
#!/usr/bin/env python3
"""Load saved session into browser."""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

async def load_session(session_num: int):
    session_dir = Path(f"sessions/session-{session_num}")
    
    # Load config
    with open(session_dir / "config.json") as f:
        config = json.load(f)
    
    # Load cookies
    with open(session_dir / "cookies.json") as f:
        cookies = json.load(f)
    
    print(f"Loading session: {config['email']}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=False,
        )
        context = await browser.new_context()
        await context.add_cookies(cookies)
        
        page = await context.new_page()
        await page.goto(config['dashboard_url'])
        
        print("✅ Session loaded!")
        print(f"Dashboard: {page.url}")
        input("Press Enter to close...")
        
        await browser.close()

if __name__ == "__main__":
    import sys
    session_num = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    asyncio.run(load_session(session_num))
```

```bash
# Save as load_session.py
python3 load_session.py 8  # Load session-8
```

### 4. Export Sessions

```bash
# Export all sessions to JSON
#!/bin/bash

output="all_sessions.json"
echo "[" > "$output"

first=true
for session_dir in sessions/session-*; do
    if [ ! "$first" = true ]; then
        echo "," >> "$output"
    fi
    first=false
    
    cat "$session_dir/config.json" >> "$output"
done

echo "]" >> "$output"

echo "✅ Exported to $output"
```

### 5. Cleanup Old Sessions

```bash
# Delete sessions older than 7 days
find sessions/ -name "session-*" -type d -mtime +7 -exec rm -rf {} \;

# Delete specific session
rm -rf sessions/session-8

# Clear all sessions
rm -rf sessions/session-*
```

## Workflow Examples

### Create Account → Use Templates

```python
#!/usr/bin/env python3
"""Create account and navigate to templates page."""

import asyncio
from lov_api import run

async def create_and_explore():
    # Create account
    result = await run(cdp_url=None)
    
    print(f"✅ Account created: {result['email']}")
    print(f"Dashboard: {result['dashboard_url']}")
    
    # Navigate to templates (browser still open)
    # User can manually explore or script can continue...

if __name__ == "__main__":
    asyncio.run(create_and_explore())
```

### Batch Account Creation

```bash
#!/bin/bash
# create_batch.sh - Create multiple accounts

count=${1:-5}  # Default 5 accounts
delay=${2:-15} # Default 15s delay

echo "Creating $count accounts with ${delay}s delay..."

for i in $(seq 1 $count); do
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Account $i/$count"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Run with auto-close
    KEEP_BROWSER_OPEN=0 python3 lov-api.py
    
    if [ $? -eq 0 ]; then
        echo "✅ Account $i created"
    else
        echo "❌ Account $i failed"
    fi
    
    if [ $i -lt $count ]; then
        echo "Waiting ${delay}s before next account..."
        sleep $delay
    fi
done

echo ""
echo "✅ Batch complete! Created $count accounts"
echo "Sessions saved in: sessions/"
```

```bash
chmod +x create_batch.sh
./create_batch.sh 10 20  # Create 10 accounts with 20s delay
```

### Monitor Script Progress

```bash
# Watch script output in real-time
python3 lov-api.py 2>&1 | tee run.log

# Or with timestamps
python3 lov-api.py 2>&1 | ts '[%Y-%m-%d %H:%M:%S]' | tee run.log
```

### Verify All Sessions

```bash
#!/bin/bash
# verify_sessions.sh - Check all saved sessions

echo "Verifying sessions..."

for session_dir in sessions/session-*; do
    if [ -f "$session_dir/config.json" ]; then
        email=$(jq -r '.email' "$session_dir/config.json")
        verified=$(jq -r '.verified' "$session_dir/config.json")
        created=$(jq -r '.created_at' "$session_dir/config.json")
        
        echo "Session: $(basename $session_dir)"
        echo "  Email: $email"
        echo "  Verified: $verified"
        echo "  Created: $created"
        echo ""
    fi
done
```

## Tips & Best Practices

### 1. Rate Limiting

**TempMailHub API has rate limits:**

```bash
# Wait between runs
python3 lov-api.py
sleep 15  # Wait 15 seconds
python3 lov-api.py
```

**If you hit rate limits:**
- Script will show: "No working mailbox after 30 attempts"
- Solution: Wait 5-10 minutes, try again

### 2. Session Management

**Keep sessions organized:**

```bash
# Name sessions meaningfully
mv sessions/session-8 sessions/production-account-1
mv sessions/session-9 sessions/testing-account-1

# Backup important sessions
cp -r sessions/session-8 backups/session-8-$(date +%Y%m%d)
```

### 3. Email Deduplication

**Used emails list grows over time:**

```bash
# Check used emails
wc -l /home/alan/Documents/used-tempmailhub-emails.txt

# Clear old emails (CAUTION: will allow reuse)
> /home/alan/Documents/used-tempmailhub-emails.txt

# Backup before clearing
cp /home/alan/Documents/used-tempmailhub-emails.txt \
   /home/alan/Documents/used-tempmailhub-emails.txt.backup
```

### 4. Browser Cleanup

**Close lingering Chrome processes:**

```bash
# Kill all Chrome processes
pkill -f "chrome.*playwright"

# Or more aggressive
pkill -9 chrome
```

### 5. Debugging

**Run with verbose output:**

```python
# Edit lov-api.py, add at top of main():
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Check specific step:**

```python
# Test email creation only
python3 -c "
import sys
sys.path.insert(0, '/home/alan/Documents/automation-toolkit/finals')
from lov_api import create_working_email

email, email_id = create_working_email()
print(f'Email: {email}')
print(f'ID: {email_id}')
"
```

## Common Workflows

### Development Workflow

```bash
# 1. Create test account
python3 lov-api.py

# 2. Load session for testing
python3 load_session.py 1

# 3. Test your app integration
# (browser is logged in)

# 4. Clean up
rm -rf sessions/session-1
```

### Production Workflow

```bash
# 1. Create production accounts
./create_batch.sh 5 30

# 2. Export credentials
./export_sessions.sh > production_accounts.json

# 3. Backup
cp production_accounts.json backups/accounts-$(date +%Y%m%d).json

# 4. Use in your application
# Read from production_accounts.json
```

### Testing Workflow

```bash
# 1. Create fresh account for each test
KEEP_BROWSER_OPEN=0 python3 lov-api.py

# 2. Run tests with session
python3 run_tests.py --session $(ls -t sessions/ | head -1)

# 3. Clean up test account
rm -rf sessions/$(ls -t sessions/ | head -1)
```

## Automation Integration

### Integrate with Existing Scripts

```python
#!/usr/bin/env python3
"""Your application using lov-api.py"""

import asyncio
import subprocess
import json
from pathlib import Path

def create_lovable_account():
    """Create account and return credentials."""
    # Run lov-api.py
    result = subprocess.run(
        ["python3", "lov-api.py"],
        cwd="/home/alan/Documents/automation-toolkit/finals",
        capture_output=True,
        text=True,
        env={"KEEP_BROWSER_OPEN": "0"}
    )
    
    if result.returncode != 0:
        raise Exception(f"Account creation failed: {result.stderr}")
    
    # Parse output
    for line in result.stdout.split('\n'):
        if line.strip().startswith('{'):
            return json.loads(line)
    
    raise Exception("Could not parse account details")

def load_session_cookies(session_num: int):
    """Load cookies from saved session."""
    session_dir = Path(f"sessions/session-{session_num}")
    with open(session_dir / "cookies.json") as f:
        return json.load(f)

# Use in your app
if __name__ == "__main__":
    # Create account
    account = create_lovable_account()
    print(f"Created: {account['email']}")
    
    # Load cookies
    cookies = load_session_cookies(account['session_number'])
    print(f"Loaded {len(cookies)} cookies")
    
    # Continue with your automation...
```

### Cron Job

```bash
# Create account daily
# crontab -e

# Run at 2 AM daily
0 2 * * * cd /home/alan/Documents/automation-toolkit/finals && KEEP_BROWSER_OPEN=0 python3 lov-api.py >> /tmp/lovable-cron.log 2>&1
```

### CI/CD Integration

```yaml
# .github/workflows/create-account.yml
name: Create Lovable Account

on:
  workflow_dispatch:  # Manual trigger
  schedule:
    - cron: '0 0 * * 0'  # Weekly

jobs:
  create:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install playwright
          playwright install chrome
      
      - name: Create account
        run: |
          cd finals
          KEEP_BROWSER_OPEN=0 python3 lov-api.py
      
      - name: Upload session
        uses: actions/upload-artifact@v3
        with:
          name: lovable-session
          path: finals/sessions/
```

## Advanced Features

### Custom Email Pool

```python
# Provide pre-validated emails
def create_from_pool(email_pool: list[tuple[str, str]]):
    """Use pre-generated email pool instead of creating on-the-fly."""
    for email, email_id in email_pool:
        try:
            # Skip validation, use directly
            return run_with_email(email, email_id)
        except FlowError:
            continue
    raise FlowError("All emails in pool failed")
```

### Parallel Creation

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def create_parallel(count: int):
    """Create multiple accounts in parallel."""
    with ThreadPoolExecutor(max_workers=3) as executor:
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(executor, run_script)
            for _ in range(count)
        ]
        results = await asyncio.gather(*tasks)
    return results

def run_script():
    """Run lov-api.py and return result."""
    import subprocess
    result = subprocess.run(
        ["python3", "lov-api.py"],
        cwd="/home/alan/Documents/automation-toolkit/finals",
        capture_output=True,
        env={"KEEP_BROWSER_OPEN": "0"}
    )
    return result.returncode == 0
```

### Session Rotation

```python
def get_next_session():
    """Round-robin session selection."""
    sessions = sorted(Path("sessions").glob("session-*"))
    
    # Track current session
    current_file = Path(".current_session")
    if current_file.exists():
        current = int(current_file.read_text())
        current = (current + 1) % len(sessions)
    else:
        current = 0
    
    current_file.write_text(str(current))
    
    return sessions[current]
```

## Performance Tuning

### Faster Polling

```python
# Reduce polling interval (default: 8s)
# Edit read_reset_link() in lov-api.py:

await asyncio.sleep(5)  # Instead of 8
```

### Shorter Timeouts

```python
# Reduce timeouts for faster failures
# Edit in lov-api.py:

reset_url = await read_reset_link(email_id, timeout=120)  # Instead of 180
await wait_for_dashboard(lovable_page, timeout=30)  # Instead of 60
```

### Connection Reuse

```python
# Keep browser open between runs
# Start browser once:
google-chrome --remote-debugging-port=9222 &

# Get CDP URL
cdp=$(curl -s localhost:9222/json | jq -r '.[0].webSocketDebuggerUrl')

# Use for all runs (saves 3-5s per run)
python3 lov-api.py --cdp-url "$cdp"
```

## Error Recovery

### Automatic Retry

```bash
#!/bin/bash
# retry_create.sh - Retry on failure

max_attempts=3
attempt=1

while [ $attempt -le $max_attempts ]; do
    echo "Attempt $attempt/$max_attempts..."
    
    if python3 lov-api.py; then
        echo "✅ Success!"
        exit 0
    fi
    
    echo "❌ Failed, retrying in 30s..."
    sleep 30
    attempt=$((attempt + 1))
done

echo "❌ All attempts failed"
exit 1
```

### Graceful Degradation

```python
try:
    result = await run(cdp_url=None)
except FlowError as e:
    # Log error
    print(f"Error: {e}")
    
    # Try fallback: direct email instead of API
    # Or: use different email provider
    # Or: manual intervention
```

## Monitoring

### Log All Runs

```bash
# Create log directory
mkdir -p logs

# Run with logging
python3 lov-api.py 2>&1 | tee "logs/run-$(date +%Y%m%d-%H%M%S).log"
```

### Success Rate Tracking

```bash
#!/bin/bash
# track_success.sh

total=0
success=0

for log in logs/run-*.log; do
    total=$((total + 1))
    if grep -q "🎉 SUCCESS!" "$log"; then
        success=$((success + 1))
    fi
done

echo "Success rate: $success/$total ($(( success * 100 / total ))%)"
```

## Documentation

See also:
- `README.md` - Overview and quick start
- `TECHNICAL.md` - Architecture and implementation details
- `TROUBLESHOOTING.md` - Common issues and solutions

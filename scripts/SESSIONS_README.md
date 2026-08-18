# Lovable Session Management

## Overview

The `lov3F.py` script automatically saves each successful Lovable account creation as a session in the `sessions/` directory. Each session contains:
- Browser cookies for staying logged in
- Email and password credentials
- Creation timestamp
- Dashboard URL

## Directory Structure

```
sessions/
├── session-1/
│   ├── config.json    # Email, password, timestamp
│   └── cookies.json   # Browser cookies
├── session-2/
│   ├── config.json
│   └── cookies.json
└── session-3/
    ├── config.json
    └── cookies.json
```

## Usage

### 1. Create New Session

Run the main script - it automatically saves the session:

```bash
export KEEP_BROWSER_OPEN=1
python3 lov3F.py
```

Output:
```
✓ Saved 15 cookies to sessions/session-1/cookies.json
✓ Saved session config to sessions/session-1/config.json
```

### 2. List All Sessions

```bash
python3 load_session.py --list
```

Output:
```
Session      Email                          Created                   Cookies   
================================================================================
session-1    testuser123@gmail.com          2026-08-11 13:45:23       15
session-2    anotheruser456@gmail.com       2026-08-11 14:12:45       15
session-3    thirduser789@gmail.com         2026-08-11 15:30:12       15
```

### 3. Load a Session

Load latest session (auto-detected):
```bash
python3 load_session.py
```

Load specific session:
```bash
python3 load_session.py 1    # Load session-1
python3 load_session.py 2    # Load session-2
```

This opens a browser with the saved cookies, so you're already logged in!

## Session Files

### config.json
```json
{
  "email": "testuser@gmail.com",
  "password": "testuser@gmail.com",
  "created_at": "2026-08-11T13:45:23.123456",
  "dashboard_url": "https://lovable.dev/dashboard",
  "tempmail_url": "https://tempmailhub.org/",
  "verified": true
}
```

### cookies.json
```json
[
  {
    "name": "session_id",
    "value": "abc123...",
    "domain": "lovable.dev",
    "path": "/",
    "expires": 1723456789,
    "httpOnly": true,
    "secure": true,
    "sameSite": "Lax"
  },
  ...
]
```

## Tips

- Sessions persist across script runs
- Cookies may expire after some time (check Lovable's session duration)
- You can manually edit config.json if needed
- Delete a session by removing its directory: `rm -rf sessions/session-1`
- Backup sessions directory to preserve accounts

## Reusing Sessions

To reuse an account in your own scripts:

```python
import json
from playwright.async_api import async_playwright

async def use_session(session_num: int):
    with open(f"sessions/session-{session_num}/config.json") as f:
        config = json.load(f)
    
    with open(f"sessions/session-{session_num}/cookies.json") as f:
        cookies = json.load(f)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        await context.add_cookies(cookies)
        
        page = await context.new_page()
        await page.goto("https://lovable.dev/dashboard")
        
        # You're logged in!
        print(f"Logged in as: {config['email']}")
```

## Security

⚠️ **IMPORTANT:**
- Sessions contain authentication cookies and credentials
- Don't commit the `sessions/` directory to git
- Add to .gitignore: `sessions/`
- Keep sessions directory secure (chmod 700)

```bash
# Add to .gitignore
echo "sessions/" >> .gitignore

# Secure permissions
chmod 700 sessions/
```

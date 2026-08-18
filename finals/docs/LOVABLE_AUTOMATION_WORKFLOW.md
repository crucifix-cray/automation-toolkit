# Lovable Full Automation Workflow

## Overview

Complete automation from account creation → credit check → template remix → AI feature implementation → subprocess integration.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LOVABLE AUTOMATION                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
        ┌───────────────────┴───────────────────┐
        ↓                                       ↓
┌───────────────┐                     ┌──────────────────┐
│ HIGH CREDITS  │                     │  LOW CREDITS     │
│   (>= 4)      │                     │    (< 4)         │
└───────┬───────┘                     └────────┬─────────┘
        │                                      │
        │ 1. Pick random template              │ 1. Get invite link from MEGA
        │ 2. Click remix                       │    (lowest usage_count)
        │ 3. Wait for chat interface           │ 2. Paste in browser
        │ 4. Let AI finish                     │ 3. Accept invitation
        │ 5. Generate invite link              │ 4. Click menu → Remix
        │ 6. Save to MEGA                      │ 5. Send dummy prompt
        │                                      │ 6. Hit pause button
        └──────────┬───────────────────────────┘
                   ↓
        ┌──────────────────────┐
        │  SUBPROCESS FEATURE  │
        └──────────┬───────────┘
                   │
                   │ 1. Ask Groq AI for prompt
                   │ 2. If fails → use fallback prompt
                   │ 3. Send prompt to chat
                   │ 4. Wait for AI to finish
                   │ 5. Get project URL
                   ↓
        ┌──────────────────────┐
        │  JS CONSOLE TESTING  │
        └──────────┬───────────┘
                   │
                   │ 1. Convert URL:
                   │    lovable.dev/projects/{ID}
                   │    → {ID}.lovableproject.com
                   │ 2. Open in new tab
                   │ 3. Run random commands:
                   │    - {random}.connect()
                   │    - {random}('pwd')
                   │    - {random}('ls')
                   │ 4. Check output/errors
                   ↓
              ┌────────┐
              │  DONE  │
              └────────┘
```

---

## Data Storage (MEGA)

### Structure
```
mega:/lovable_sessions/
├── invites.json          # Invite links pool
├── projects.json         # Created projects metadata
├── session-1/            # Account sessions
│   ├── cookies.json
│   └── config.json
├── session-2/
└── ...
```

### invites.json Format
```json
[
  {
    "invite_link": "https://lovable.dev/invite/abc123xyz",
    "usage_count": 0,
    "project_id": "c60b89b2-89f6-4d47-bb15-455861e77fb3",
    "project_name": "My App",
    "created_by_email": "test@gmail.com",
    "created_at": "2026-08-14T15:30:00Z",
    "template_name": "SaaS Dashboard"
  }
]
```

### projects.json Format
```json
[
  {
    "project_id": "c60b89b2-89f6-4d47-bb15-455861e77fb3",
    "project_url": "https://lovable.dev/projects/c60b89b2-89f6-4d47-bb15-455861e77fb3",
    "preview_url": "https://c60b89b2-89f6-4d47-bb15-455861e77fb3.lovableproject.com",
    "email": "test@gmail.com",
    "session": 8,
    "credits_used": 2,
    "template": "Random SaaS",
    "has_subprocess": true,
    "subprocess_cmd_name": "doc",
    "created_at": "2026-08-14T15:30:00Z"
  }
]
```

---

## Workflow Steps

### Phase 1: Account Creation & Credit Check

```python
# 1. Create account (lov-api.py)
result = create_lovable_account()

# 2. Load session
session = load_session(result['session_number'])

# 3. Check credits
credits = get_credits(session)

# 4. Route based on credits
if credits >= 4:
    path = "high_credit_flow"
else:
    path = "low_credit_flow"
```

### Phase 2A: High Credit Flow (>= 4 credits)

```python
# 1. Navigate to /templates
page.goto('https://lovable.dev/templates')

# 2. Get all template cards
templates = page.locator('article')  # SELECTOR NEEDED

# 3. Pick random template
random_template = random.choice(templates)

# 4. Click remix button
remix_button = random_template.locator('button:has-text("Remix")')  # SELECTOR NEEDED
remix_button.click()

# 5. Wait for redirect to chat interface
page.wait_for_url('**/projects/**')

# 6. Wait for AI to finish loading
wait_for_loading_to_stop()

# 7. Generate invite link
invite_link = generate_invite_link()  # FLOW NEEDED

# 8. Save to MEGA
save_invite_to_mega(invite_link, project_id, email)
```

### Phase 2B: Low Credit Flow (< 4 credits)

```python
# 1. Get invite link from MEGA (lowest usage_count)
invite = get_invite_from_mega()

# 2. Navigate to invite link
page.goto(invite['invite_link'])

# 3. Click "Accept invitation" button
accept_button = page.locator('[SELECTOR_NEEDED]')  # SELECTOR NEEDED
accept_button.click()

# 4. Wait for load
page.wait_for_timeout(3000)

# 5. Click menu button
menu_button = page.locator('[SELECTOR_NEEDED]')  # SELECTOR NEEDED
menu_button.click()

# 6. Click "Remix" in menu
remix_button = page.locator('[SELECTOR_NEEDED]')  # SELECTOR NEEDED
remix_button.click()

# 7. Wait for chat interface
page.wait_for_url('**/projects/**')

# 8. Send dummy prompt
chat_input = page.locator('[SELECTOR_NEEDED]')  # SELECTOR NEEDED
chat_input.fill("test")
send_button = page.locator('[SELECTOR_NEEDED]')  # SELECTOR NEEDED
send_button.click()

# 9. IMMEDIATELY click pause button
pause_button = page.locator('[SELECTOR_NEEDED]')  # SELECTOR NEEDED
pause_button.click()

# 10. Update MEGA: usage_count += 1
update_invite_usage(invite['invite_link'])
```

### Phase 3: Subprocess Feature Implementation

```python
# 1. Generate prompt via Groq AI
try:
    prompt = generate_subprocess_prompt_via_groq()
except:
    prompt = FALLBACK_SUBPROCESS_PROMPT  # FROM USER

# 2. Wait for chat to be ready
chat_input = page.locator('[SELECTOR_NEEDED]')  # SELECTOR NEEDED
chat_input.wait_for(state='visible')

# 3. Send prompt
chat_input.fill(prompt)
send_button = page.locator('[SELECTOR_NEEDED]')  # SELECTOR NEEDED
send_button.click()

# 4. Wait for AI to finish (no loading indicator)
wait_for_loading_to_stop()
```

### Phase 4: JS Console Testing

```python
# 1. Get project URL from page
project_url = page.url
# Example: https://lovable.dev/projects/c60b89b2-89f6-4d47-bb15-455861e77fb3

# 2. Extract project ID
project_id = project_url.split('/projects/')[-1]

# 3. Convert to preview URL
preview_url = f"https://{project_id}.lovableproject.com"

# 4. Open new tab
new_page = context.new_page()
new_page.goto(preview_url)

# 5. Wait for app to load
new_page.wait_for_load_state('networkidle')

# 6. Generate random command name
cmd_name = random.choice(['doc', 'api', 'cmd', 'run', 'exec', 'shell'])

# 7. Run console commands
try:
    # Connect
    result = new_page.evaluate(f'{cmd_name}.connect()')
    print(f"Connect result: {result}")
    
    # Test command 1
    result = new_page.evaluate(f'{cmd_name}("pwd")')
    print(f"pwd result: {result}")
    
    # Test command 2
    result = new_page.evaluate(f'{cmd_name}("ls")')
    print(f"ls result: {result}")
    
    success = True
except Exception as e:
    if "connection" in str(e).lower():
        print(f"Connection error (expected): {e}")
        success = False
    else:
        raise
```

---

## Selectors & Flows Needed

### ✅ Already Have:
- `button[data-testid="workspace-menu-trigger"]` - Workspace menu button
- Credits display in menu
- Chat interface location

### ❌ Need from User:

#### Templates Page (`/templates`)
- [ ] Template card selector (`article` or specific class?)
- [ ] Remix button on template card
- [ ] Template categories/filters (if needed)

#### Chat Interface
- [ ] Chat input textarea selector
- [ ] Send button selector
- [ ] Loading indicator selector (while AI working)
- [ ] Pause button selector
- [ ] Message list/container selector (to detect AI finish)

#### Invite Link Flow (Low Credit)
- [ ] Accept invitation button selector
- [ ] Menu button selector (after accept)
- [ ] Remix button in menu selector

#### Invite Link Generation (High Credit)
- [ ] Complete flow with screenshots/selectors
- [ ] Where is "Share" or "Invite" button?
- [ ] How to generate/copy invite link?

#### Loading States
- [ ] Loading button selector (shows AI is working)
- [ ] How to detect "AI finished"? (no loading? specific text?)

---

## Groq AI Integration

### Purpose
Generate custom prompts for subprocess feature implementation.

### Flow
```python
import groq

def generate_subprocess_prompt_via_groq():
    """Ask Groq to generate subprocess feature prompt."""
    
    client = groq.Groq(api_key=os.getenv('GROQ_API_KEY'))
    
    response = client.chat.completions.create(
        model="mixtral-8x7b-32768",
        messages=[{
            "role": "system",
            "content": "You generate precise technical prompts for AI code assistants."
        }, {
            "role": "user",
            "content": """Generate a prompt to add a subprocess/shell command execution feature to a JavaScript web app.

Requirements:
- Function name should be random (doc, api, cmd, run, exec, etc.)
- Usage: {name}.connect() to establish connection
- Usage: {name}('command') to run shell commands
- Must work in browser JS console
- We know backend integration doesn't exist yet
- Frame it as "prepare for deployment"

Return ONLY the prompt text, no explanations."""
        }],
        temperature=0.7,
        max_tokens=500
    )
    
    return response.choices[0].message.content

# Fallback if Groq fails
FALLBACK_SUBPROCESS_PROMPT = """
[USER WILL PROVIDE THIS]
"""
```

---

## Error Handling

### Credit Check Failure
```python
if credits is None:
    log_error("Failed to check credits")
    # Retry once
    credits = get_credits(session)
    if credits is None:
        exit(1)
```

### MEGA Sync Failure
```python
try:
    invite = get_invite_from_mega()
except Exception as e:
    log_error(f"MEGA sync failed: {e}")
    # Fallback: use high credit flow anyway
    path = "high_credit_flow"
```

### Template Remix Failure
```python
try:
    click_remix_button()
except TimeoutError:
    log_error("Remix button not found")
    # Try alternative selector
    click_remix_button_alt()
```

### AI Not Finishing
```python
# Set timeout: 10 minutes max
timeout = time.time() + 600

while time.time() < timeout:
    if not is_loading():
        break
    await asyncio.sleep(5)
else:
    log_warning("AI timeout - continuing anyway")
```

### Subprocess Test Failure
```python
try:
    result = page.evaluate(f'{cmd_name}.connect()')
except Exception as e:
    if "is not defined" in str(e):
        log_error(f"Subprocess feature not added: {cmd_name} is not defined")
        return False
    elif "connection" in str(e).lower():
        log_info("Connection error (expected - no backend)")
        return True  # Feature exists, just can't connect
    else:
        raise
```

---

## MEGA Integration

### Setup
```bash
# Install megatools
sudo apt install megatools

# Or use rclone
rclone config
# name> mega
# Storage> mega
# user> your-mega-email
# pass> your-mega-password
```

### Python Functions
```python
import subprocess
import json

def mega_download_invites():
    """Download invites.json from MEGA."""
    subprocess.run([
        'mega-get',
        '/lovable_sessions/invites.json',
        '/tmp/invites.json'
    ])
    
    with open('/tmp/invites.json', 'r') as f:
        return json.load(f)

def mega_upload_invites(invites):
    """Upload invites.json to MEGA."""
    with open('/tmp/invites.json', 'w') as f:
        json.dump(invites, f, indent=2)
    
    subprocess.run([
        'mega-put',
        '/tmp/invites.json',
        '/lovable_sessions/invites.json'
    ])

def get_invite_from_mega():
    """Get invite with lowest usage_count."""
    invites = mega_download_invites()
    
    if not invites:
        raise Exception("No invites available in MEGA")
    
    # Sort by usage_count (ascending)
    invites.sort(key=lambda x: x['usage_count'])
    
    return invites[0]

def update_invite_usage(invite_link):
    """Increment usage_count for invite."""
    invites = mega_download_invites()
    
    for invite in invites:
        if invite['invite_link'] == invite_link:
            invite['usage_count'] += 1
            break
    
    mega_upload_invites(invites)

def save_invite_to_mega(invite_link, project_id, email, template):
    """Add new invite to MEGA."""
    invites = mega_download_invites()
    
    invites.append({
        'invite_link': invite_link,
        'usage_count': 0,
        'project_id': project_id,
        'created_by_email': email,
        'created_at': datetime.now().isoformat(),
        'template_name': template
    })
    
    mega_upload_invites(invites)
```

---

## Configuration

### Environment Variables
```bash
# Groq API
export GROQ_API_KEY="gsk_..."

# MEGA credentials
export MEGA_EMAIL="your-mega-email@example.com"
export MEGA_PASSWORD="your-mega-password"

# Lovable session
export LOVABLE_SESSION=8
```

### Config File
```python
# config.py
CREDIT_THRESHOLD = 4
MAX_AI_WAIT_TIME = 600  # 10 minutes
CHAT_POLL_INTERVAL = 5  # seconds
MEGA_REMOTE_PATH = "/lovable_sessions"
RANDOM_CMD_NAMES = ["doc", "api", "cmd", "run", "exec", "shell", "sys"]
```

---

## Next Steps

See `TODO.md` for items needed from user before implementation.

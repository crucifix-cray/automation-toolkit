# Implementation TODOs - Lovable Full Automation

## 🎯 GOAL
Complete end-to-end automation: Account → Credits → Templates → AI Build → Subprocess → Console Test → MEGA Storage

---

## ✅ PHASE 1: FOUNDATION (DONE)

- [x] Account creation script (`lov-api.py`)
  - Email via TempMailHub API
  - Session saving to `/sessions/session-N/`
  - Email deduplication
  - WARP integration with fallback
  
- [x] Credit checker (`get_credits_final.py`)
  - Extract credits from workspace menu
  - `--headless` flag support
  - Session loading
  
- [x] Documentation structure
  - README.md
  - TECHNICAL.md
  - USAGE.md
  - TROUBLESHOOTING.md
  - TODO.md (user inputs needed)
  - LOVABLE_AUTOMATION_WORKFLOW.md (architecture)

---

## ❌ PHASE 2: SELECTOR DISCOVERY (BLOCKED - NEED USER)

### 2.1 Templates Page Selectors
- [ ] Load browser with session-8
- [ ] Navigate to `https://lovable.dev/templates`
- [ ] Inspect template cards
  - [ ] Get template card selector
  - [ ] Get remix/use button selector
  - [ ] Test clicking random template
- [ ] Document in `SELECTORS.md`

### 2.2 Chat Interface Selectors
- [ ] Remix a template manually
- [ ] Wait for chat interface to load
- [ ] Inspect elements:
  - [ ] Chat input textarea
  - [ ] Send message button
  - [ ] Loading indicator/spinner
  - [ ] Pause button
  - [ ] Message container
- [ ] Test detecting "AI finished" state
- [ ] Document in `SELECTORS.md`

### 2.3 Invite Link Generation Flow
- [ ] In high-credit project, find share/invite option
- [ ] Document complete flow:
  - [ ] Where to click (selector)
  - [ ] Modal/dropdown that appears
  - [ ] Generate invite button
  - [ ] Copy/extract invite link
  - [ ] URL format validation
- [ ] Test flow end-to-end
- [ ] Document in `SELECTORS.md`

### 2.4 Invite Link Acceptance Flow
- [ ] Create test invite link
- [ ] Open in new browser/incognito
- [ ] Document complete flow:
  - [ ] URL loads → what page?
  - [ ] Accept invitation button
  - [ ] Redirect behavior
  - [ ] Menu button location
  - [ ] Remix option in menu
  - [ ] Redirect to chat interface
- [ ] Test flow end-to-end
- [ ] Document in `SELECTORS.md`

---

## ❌ PHASE 3: MEGA INTEGRATION (READY TO CODE)

### 3.1 MEGA Setup
- [ ] Confirm MEGA credentials
  - [ ] Email: `________________`
  - [ ] Password: `________________`
  - [ ] Or use existing config from repo?
  
- [ ] Test MEGA connection
  ```bash
  mega-login "email" "password"
  mega-whoami
  mega-ls /
  ```

- [ ] Create remote structure
  ```bash
  mega-mkdir /lovable_sessions
  mega-put empty_invites.json /lovable_sessions/invites.json
  ```

### 3.2 MEGA Python Module
- [ ] Create `mega_client.py`
  - [ ] `download_invites()` - Get invites.json
  - [ ] `upload_invites()` - Save invites.json
  - [ ] `get_lowest_usage_invite()` - Get invite with min usage_count
  - [ ] `increment_invite_usage(link)` - Update usage_count
  - [ ] `add_invite(link, project_id, email, template)` - Add new invite
  - [ ] `download_projects()` - Get projects.json
  - [ ] `upload_projects()` - Save projects.json
  - [ ] `add_project(data)` - Add project metadata

- [ ] Test MEGA functions
  - [ ] Create test invites.json
  - [ ] Upload/download cycle
  - [ ] Update operations
  - [ ] Error handling

- [ ] Document in `docs/MEGA.md`

---

## ❌ PHASE 4: CORE AUTOMATION SCRIPT (READY TO CODE AFTER SELECTORS)

### 4.1 Main Script Structure
- [ ] Create `lovable-full-automation.py`
  - [ ] Import existing modules (lov-api, get_credits_final)
  - [ ] Import MEGA client
  - [ ] Command-line args:
    - [ ] `--create-account` (or load existing session)
    - [ ] `--session N` (use specific session)
    - [ ] `--headless` (run headless)
    - [ ] `--no-warp` (skip WARP)
    - [ ] `--groq-key KEY` (Groq API key)
    - [ ] `--fallback-prompt FILE` (fallback prompt path)

### 4.2 Credit Routing Logic
- [ ] Implement `check_credits_and_route()`
  - [ ] Call get_credits_final.py logic
  - [ ] If credits >= 4: `high_credit_flow()`
  - [ ] If credits < 4: `low_credit_flow()`
  - [ ] Handle credit check failures

### 4.3 High Credit Flow
- [ ] Implement `high_credit_flow()`
  - [ ] Navigate to /templates
  - [ ] Get all template cards
  - [ ] Pick random template
  - [ ] Click remix button
  - [ ] Wait for chat interface
  - [ ] Wait for AI to finish loading
  - [ ] Generate invite link (call helper)
  - [ ] Save to MEGA
  - [ ] Continue to subprocess phase

- [ ] Implement `generate_invite_link(page)`
  - [ ] Follow documented flow
  - [ ] Return invite link string
  - [ ] Handle errors

### 4.4 Low Credit Flow
- [ ] Implement `low_credit_flow()`
  - [ ] Get invite from MEGA (lowest usage)
  - [ ] Navigate to invite URL
  - [ ] Click "Accept invitation"
  - [ ] Wait for load
  - [ ] Click menu button
  - [ ] Click "Remix"
  - [ ] Wait for chat interface
  - [ ] Send dummy prompt
  - [ ] IMMEDIATELY click pause
  - [ ] Update invite usage in MEGA
  - [ ] Continue to subprocess phase

### 4.5 Subprocess Feature Phase
- [ ] Implement `add_subprocess_feature(page, project_url)`
  - [ ] Generate random command name
  - [ ] Get prompt (Groq or fallback)
  - [ ] Wait for chat input ready
  - [ ] Send prompt
  - [ ] Wait for AI to finish
  - [ ] Return command name for testing

- [ ] Implement `generate_subprocess_prompt(cmd_name)`
  - [ ] Try Groq API first
  - [ ] Fallback to file if Groq fails
  - [ ] Template variables: {cmd_name}
  - [ ] Return formatted prompt

### 4.6 Console Testing Phase
- [ ] Implement `test_subprocess_feature(page, project_url, cmd_name)`
  - [ ] Extract project ID from URL
  - [ ] Convert to preview URL: `{id}.lovableproject.com`
  - [ ] Open new tab
  - [ ] Wait for app load
  - [ ] Run JS console commands:
    - [ ] `{cmd_name}.connect()`
    - [ ] `{cmd_name}('pwd')`
    - [ ] `{cmd_name}('ls')`
  - [ ] Capture output/errors
  - [ ] Determine success:
    - SUCCESS: Connection error (no backend)
    - FAILURE: `{cmd_name} is not defined`
  - [ ] Return test results

---

## ❌ PHASE 5: GROQ AI INTEGRATION (OPTIONAL)

### 5.1 Groq Setup
- [ ] Get Groq API key from user
  - [ ] Or set as env var: `GROQ_API_KEY`
  
- [ ] Test Groq connection
  ```python
  import groq
  client = groq.Groq(api_key=KEY)
  response = client.chat.completions.create(...)
  ```

### 5.2 Prompt Generation
- [ ] Create `groq_prompts.py`
  - [ ] `generate_subprocess_prompt(cmd_name)` 
  - [ ] System prompt for code assistant
  - [ ] User prompt template
  - [ ] Temperature: 0.7
  - [ ] Max tokens: 500
  - [ ] Error handling + fallback

- [ ] Get fallback prompt from user
  - [ ] Save to `prompts/subprocess_fallback.txt`
  - [ ] Variables: `{cmd_name}` for substitution

- [ ] Test prompt generation
  - [ ] Multiple runs (check variety)
  - [ ] Fallback when Groq fails
  - [ ] Validate prompt quality

---

## ❌ PHASE 6: ERROR HANDLING & LOGGING

### 6.1 Error Handlers
- [ ] Credit check failure
  - [ ] Retry once
  - [ ] Exit if still fails
  
- [ ] MEGA connection failure
  - [ ] Retry 3 times
  - [ ] Fallback to high-credit flow if persistent
  
- [ ] Template remix failure
  - [ ] Try alternative selectors
  - [ ] Try different template
  - [ ] Exit after 3 failures
  
- [ ] AI timeout (takes too long)
  - [ ] Max wait: 10 minutes
  - [ ] Continue anyway if timeout
  - [ ] Log warning
  
- [ ] Invite link generation failure
  - [ ] Log error
  - [ ] Continue without saving to MEGA
  
- [ ] Subprocess test failure
  - [ ] Log result
  - [ ] Save to report
  - [ ] Don't exit (informational only)

### 6.2 Logging System
- [ ] Create `logger.py`
  - [ ] Console output (colored)
  - [ ] File output (timestamped logs)
  - [ ] Log levels: DEBUG, INFO, WARNING, ERROR
  - [ ] Session-specific log files
  
- [ ] Log key events:
  - [ ] Account creation
  - [ ] Credit check result
  - [ ] Flow routing decision
  - [ ] Template selection
  - [ ] AI build progress
  - [ ] Subprocess prompt sent
  - [ ] Console test results
  - [ ] MEGA sync operations
  - [ ] Errors with stack traces

---

## ❌ PHASE 7: TESTING & VALIDATION

### 7.1 Unit Tests
- [ ] Test MEGA functions
  - [ ] Upload/download
  - [ ] Invite management
  - [ ] Project metadata
  
- [ ] Test credit checker
  - [ ] Parse credits correctly
  - [ ] Handle missing credits
  
- [ ] Test URL conversion
  - [ ] lovable.dev/projects/{id} → {id}.lovableproject.com
  
- [ ] Test random selection
  - [ ] Template picker
  - [ ] Command name generator

### 7.2 Integration Tests
- [ ] High credit flow (end-to-end)
  - [ ] With real account
  - [ ] Record all steps
  - [ ] Verify invite link created
  
- [ ] Low credit flow (end-to-end)
  - [ ] With real account + invite
  - [ ] Verify usage_count incremented
  - [ ] Verify project accessible
  
- [ ] Subprocess feature
  - [ ] Multiple command names
  - [ ] Verify feature added
  - [ ] Test console execution

### 7.3 Edge Cases
- [ ] No invites in MEGA (low credit path)
  - [ ] Expected behavior: Exit with error
  
- [ ] Invalid invite link
  - [ ] Expected behavior: Log error, try next invite
  
- [ ] Network failures
  - [ ] Expected behavior: Retry with exponential backoff
  
- [ ] Browser crashes
  - [ ] Expected behavior: Save state, restart

---

## ❌ PHASE 8: DOCUMENTATION & POLISH

### 8.1 Code Documentation
- [ ] Docstrings for all functions
- [ ] Type hints
- [ ] Inline comments for complex logic
- [ ] Examples in docstrings

### 8.2 User Documentation
- [ ] Update `README.md`
  - [ ] Installation steps
  - [ ] Configuration
  - [ ] Usage examples
  - [ ] Troubleshooting
  
- [ ] Create `SELECTORS.md`
  - [ ] All selectors with descriptions
  - [ ] How to update if page changes
  
- [ ] Create `MEGA.md`
  - [ ] Setup instructions
  - [ ] Data structure
  - [ ] Manual operations
  
- [ ] Update `USAGE.md`
  - [ ] Command-line options
  - [ ] Environment variables
  - [ ] Example workflows

### 8.3 Configuration Files
- [ ] `config.py` - Script settings
- [ ] `prompts/subprocess_fallback.txt` - Default prompt
- [ ] `.env.example` - Environment variables template
- [ ] `requirements.txt` - Python dependencies

---

## ❌ PHASE 9: DEPLOYMENT & SCALING

### 9.1 Batch Processing
- [ ] Create `batch-automation.sh`
  - [ ] Run N accounts in sequence
  - [ ] Delay between runs
  - [ ] Stop on first error (optional)
  - [ ] Summary report at end

### 9.2 Parallel Execution
- [ ] Create `parallel-automation.py`
  - [ ] Run M accounts simultaneously
  - [ ] Use asyncio + multiple browsers
  - [ ] Shared MEGA lock (avoid conflicts)
  - [ ] Progress dashboard

### 9.3 Monitoring
- [ ] Create status dashboard
  - [ ] Accounts created: X
  - [ ] Projects with subprocess: Y
  - [ ] Invites in pool: Z
  - [ ] Success rate: %
  
- [ ] Create reports
  - [ ] Daily summary
  - [ ] Error log
  - [ ] Resource usage

### 9.4 Railway/Cloud Deployment
- [ ] Dockerfile
- [ ] Railway config
- [ ] MEGA credentials via env vars
- [ ] Headless mode by default
- [ ] Continuous mode with stop signal

---

## 🎯 CURRENT PRIORITY ORDER

### 🔥 CRITICAL (DO FIRST)
1. **Phase 2.1-2.4:** Get all selectors from user
2. **Phase 3.1:** Confirm MEGA credentials
3. **Phase 4.1:** Create main script skeleton

### ⚡ HIGH (DO NEXT)
4. **Phase 3.2:** Build MEGA integration
5. **Phase 4.2-4.4:** Implement credit routing + flows
6. **Phase 4.5:** Add subprocess feature logic
7. **Phase 4.6:** Add console testing

### 📋 MEDIUM (AFTER CORE WORKS)
8. **Phase 5:** Groq AI integration
9. **Phase 6:** Error handling + logging
10. **Phase 7:** Testing

### 🎨 LOW (POLISH)
11. **Phase 8:** Documentation
12. **Phase 9:** Scaling features

---

## 📊 COMPLETION STATUS

### Overall Progress: 15%

- ✅ Phase 1: 100% (Foundation complete)
- ❌ Phase 2: 0% (Blocked - need user input)
- ❌ Phase 3: 0% (Ready to start)
- ❌ Phase 4: 0% (Blocked on Phase 2)
- ❌ Phase 5: 0% (Optional)
- ❌ Phase 6: 0% (After Phase 4)
- ❌ Phase 7: 0% (After Phase 4)
- ❌ Phase 8: 20% (Docs structure done)
- ❌ Phase 9: 0% (After everything works)

---

## 🚦 NEXT ACTION

**IMMEDIATE:** User provides selectors/flows (see `TODO.md`)

**THEN:** 
1. Create `SELECTORS.md` with all discovered selectors
2. Test MEGA setup
3. Start Phase 4 (main script)

**BLOCKERS:**
- Waiting on user for templates page selectors
- Waiting on user for chat interface selectors
- Waiting on user for invite link flows
- Waiting on user for subprocess prompt text
- Waiting on user for MEGA credentials (or confirm existing)
- Waiting on user for Groq API key (optional)

---

## 📝 NOTES

- Keep sessions open after success (for debugging)
- Always log project URLs for manual inspection
- Test with session-8 first (5 credits left)
- Consider creating new account for full flow test
- MEGA operations should be atomic (download → modify → upload)
- Random command names prevent detection patterns

---

**READY TO START AS SOON AS USER PROVIDES SELECTORS!**

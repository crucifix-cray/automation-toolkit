#!/usr/bin/env python3
"""
Lovable Invite Automation
Accept invite → Remix → Send prompt → Test subprocess in parallel tabs

Flow:
- Load session → Accept invite link → Remix project
- Send "1+1" prompt → Wait 1 min → Open preview tab
- Wait for "lovable" console message (5 min, retry refresh 5x)
- Test window.doc commands → Keep both tabs alive 45-60 min
"""

import asyncio
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from invisible_playwright.async_api import InvisiblePlaywright

# Paths
SCRIPT_DIR = Path(__file__).parent
SESSIONS_DIR = Path("/home/alan/Documents/automation-toolkit/scripts/sessions")
SELECTORS_FILE = Path("/home/alan/Documents/automation-toolkit/finals/docs/SELECTORS_COMPLETE.json")
REAL_COOKIES_PATH = Path("/home/alan/Documents/automation-toolkit/finals/real_browser_cookies.json")

# Load selectors
with open(SELECTORS_FILE) as f:
    SELECTORS = json.load(f)


def log(msg: str, level: str = "INFO"):
    """Simple logger."""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {level}: {msg}", flush=True)


async def wait(ms: int = 500, max_ms: int = None):
    """Fixed delay with optional random range."""
    if max_ms is not None:
        delay = random.randint(ms, max_ms)
    else:
        delay = ms
    await asyncio.sleep(delay / 1000)


async def js_click(page, locator, description: str = ""):
    """Direct JavaScript click."""
    try:
        await locator.wait_for(state="attached", timeout=5000)
    except:
        pass
    
    await page.evaluate("el => el.click()", await locator.element_handle())
    if description:
        log(f"✅ {description}")
    await wait(500)


async def accept_invite_and_remix(page, invite_link: str, email: str):
    """Accept invite link and remix the project - USES LOW_CREDIT_FLOW from main script."""
    
    # 1. Navigate to invite link
    log(f"Opening invite link...")
    try:
        await page.goto(invite_link, timeout=60000)
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
    except Exception as e:
        log(f"⚠️  Page load issue: {e}", "WARNING")

    await wait(3000)

    # 2. Check if already logged in
    current_url = page.url

    if "projects" not in current_url or "login" in current_url:
        log("Not logged in, signing in...")
        try:
            sign_in_btn = page.get_by_role("button", name="Sign in").first
            await js_click(page, sign_in_btn, "Click Sign in")
            await page.wait_for_url("**/login", timeout=15000)
            await page.wait_for_url("**/projects/**", timeout=30000)
        except Exception as e:
            log(f"⚠️  Login flow issue: {e}", "WARNING")

    # 3. Accept invitation modal - keep clicking until dialog disappears
    log("Accepting invitation...")
    try:
        await wait(2000)
        
        # Try up to 5 times to click Accept invitation
        for attempt in range(1, 6):
            try:
                # Check if dialog is still visible
                invite_dialog = page.locator('div[role="dialog"]')
                if not await invite_dialog.is_visible(timeout=2000):
                    log("✅ Invitation dialog gone!")
                    break
                
                # Find and click Accept invitation button - USE REGULAR CLICK, NOT JS
                accept_btn = page.locator('button:has-text("Accept invitation")')
                if await accept_btn.is_visible(timeout=2000):
                    log(f"  Attempt {attempt}: Clicking Accept invitation...")
                    await accept_btn.click(timeout=3000)  # Regular click, not js_click
                    log(f"  ✅ Clicked (attempt {attempt})")
                    await wait(2000)
                else:
                    log("  No Accept button visible, dialog might be gone")
                    break
            except Exception as e:
                log(f"  Attempt {attempt} error: {e}")
                # Try one more time with force
                try:
                    await accept_btn.click(force=True, timeout=2000)
                    log(f"  ✅ Force clicked (attempt {attempt})")
                    await wait(2000)
                except:
                    break
        
        log("✅ Invitation accepted")
        await wait(3000)
    except Exception as e:
        log(f"⚠️  Invitation acceptance issue: {e}", "WARNING")

    # 4. Dismiss cookie banner
    try:
        cookie_btn = page.get_by_role("button", name="Accept all")
        await js_click(page, cookie_btn, "Accept cookies")
    except:
        pass

    # 5. Wait for project to load after invitation acceptance
    log("Waiting for project menu to appear...")
    
    # Don't wait blindly - check if chat is ready (means editor loaded)
    chat_ready = False
    for i in range(60):  # Check for 60 seconds max
        try:
            # Check if chat input is visible (means editor loaded)
            chat_check = page.locator('div[contenteditable="true"][role="textbox"]').first
            if await chat_check.is_visible(timeout=1000):
                chat_ready = True
                log(f"✅ Editor loaded (chat ready after {i+1}s)")
                break
        except:
            pass
        await wait(1000)
    
    if not chat_ready:
        log("⚠️  Chat not ready after 60s, proceeding anyway...")
    
    current_url = page.url
    log(f"Current URL: {current_url}")

    # 6. REMIX the project (make our own copy)
    log("Remixing project...")
    try:
        # Wait for and click project menu button
        menu_btn = page.locator('[data-testid="editor-nav-project-menu"]')
        await menu_btn.wait_for(state="attached", timeout=120000)
        
        # Try regular click first (with position to avoid scroll issues)
        try:
            box = await menu_btn.bounding_box()
            if box:
                # Try clicking with element handle directly
                handle = await menu_btn.element_handle()
                if handle:
                    # Simulate real DOM click using CDP
                    await handle.click()
                    await wait(2000)
                    log("✅ Clicked project menu button")
                else:
                    raise Exception("No element handle")
        except Exception as e:
            log(f"⚠️  Click failed: {e}, trying mouse click...")
            await page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            await wait(2000)
            log("✅ Clicked project menu button (mouse)")

        # Click "Remix" menuitem in dropdown
        remix_item = page.locator('div[role="menuitem"]:has-text("Remix")').first
        
        # Check if menu appeared, retry up to 3 times
        for retry in range(3):
            try:
                await remix_item.wait_for(state="visible", timeout=3000)
                break
            except:
                if retry < 2:
                    log(f"⚠️  Remix menuitem not visible, retry {retry+1}/3...")
                    # Click menu button again
                    handle = await menu_btn.element_handle()
                    if handle:
                        await handle.click()
                    await wait(1500)
                else:
                    log("❌ Menu not opening after 3 attempts, taking screenshot...")
                    await page.screenshot(path="/tmp/lovable-no-menu.png")
                    raise Exception("Remix menu item not appearing after 3 clicks")
        
        # Click Remix menuitem
        remix_handle = await remix_item.element_handle()
        if remix_handle:
            await remix_handle.click()
            log("✅ Clicked Remix menuitem")
        else:
            raise Exception("Could not get remix item handle")

        # Wait for remix dialog to appear
        await wait(2000, 3000)
        log("📝 Handling remix dialog...")

        # HUMAN BEHAVIOR: Retype the project title
        try:
            title_input = page.locator('input[id="project-title"]')
            if await title_input.is_visible(timeout=3000):
                current_title = await title_input.input_value()
                log(f"Current title: {current_title}")

                await title_input.click(timeout=2000)
                await wait(300, 600)

                await page.keyboard.press("Control+a")
                await wait(200, 400)
                await page.keyboard.press("Backspace")
                await wait(400, 800)

                for char in current_title:
                    await page.keyboard.type(char)
                    await asyncio.sleep(random.randint(80, 200) / 1000)
                    if random.random() < 0.15:
                        await wait(300, 700)

                log("✅ Retyped project title like a human")
                await wait(800, 1500)
        except Exception as e:
            log(f"⚠️  Could not retype title: {e}")

        # Check if warning appears (not allowed to create projects)
        warning = page.locator('p:has-text("You are not allowed to create projects")')
        try:
            if await warning.is_visible(timeout=2000):
                log("⚠️  Workspace not allowed, changing workspace...")

                workspace_dropdown = page.locator('button[id="remix-target-workspace"]')
                await workspace_dropdown.click(timeout=2000)
                await wait(1000, 1500)

                workspace_options = page.locator('div[role="option"]')
                count = await workspace_options.count()
                if count > 1:
                    await workspace_options.nth(1).click(timeout=2000)
                    log("✅ Changed workspace")
                    await wait(500, 1000)
                    
                    # IMPORTANT: After changing workspace, title input needs re-editing
                    log("Re-editing title after workspace change...")
                    try:
                        title_input = page.locator('input[id="project-title"]')
                        if await title_input.is_visible(timeout=3000):
                            current_title = await title_input.input_value()
                            
                            await title_input.click(timeout=2000)
                            await wait(300, 600)

                            await page.keyboard.press("Control+a")
                            await wait(200, 400)
                            await page.keyboard.press("Backspace")
                            await wait(400, 800)

                            for char in current_title:
                                await page.keyboard.type(char)
                                await asyncio.sleep(random.randint(80, 200) / 1000)
                                if random.random() < 0.15:
                                    await wait(300, 700)

                            log("✅ Re-typed title after workspace change")
                            await wait(800, 1500)
                    except Exception as e:
                        log(f"⚠️  Could not re-type title: {e}")
        except:
            log("No workspace warning")

        # Check checkbox - USE REGULAR CLICK
        try:
            checkbox = page.locator('button[id="security-acknowledgement"]')
            await checkbox.wait_for(state="visible", timeout=3000)
            await checkbox.click(timeout=2000)
            log("✅ Checked security acknowledgement")
            await wait(800, 1500)
        except:
            log("⚠️  No checkbox found, skipping")

        # Click submit button - TRY MULTIPLE SELECTORS
        log("Looking for submit button...")
        submit_btn = None
        
        # Try multiple button selectors
        button_selectors = [
            'button[type="submit"]:has-text("Acknowledge and remix")',
            'button:has-text("Acknowledge and remix")',
            'button[type="submit"]:has-text("Remix")',
            'button:has-text("Remix")',
            'button[type="submit"]',
        ]
        
        for selector in button_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=2000):
                    submit_btn = btn
                    log(f"✅ Found button: {selector}")
                    break
            except:
                continue
        
        if not submit_btn:
            log("❌ Could not find submit button - taking screenshot", "ERROR")
            await page.screenshot(path="/tmp/lovable-remix-no-button.png")
            raise Exception("Submit button not found in dialog")

        # Wait for button to be ENABLED
        log("Waiting for submit button to be enabled...")
        try:
            for i in range(20):
                is_disabled = await submit_btn.get_attribute("disabled")
                if is_disabled is None:
                    log("✅ Submit button is enabled")
                    break
                await wait(500)
            else:
                log("⚠️ Button still disabled after 10s, trying anyway...")
        except:
            pass

        # Bring button into center
        try:
            box = await submit_btn.bounding_box()
            if box:
                viewport_height = await page.evaluate("window.innerHeight")
                scroll_y = box['y'] - (viewport_height / 2) + (box['height'] / 2)
                await page.evaluate(f"window.scrollTo(0, {scroll_y})")
                await wait(1)
                log("✅ Brought button into viewport center")
        except:
            pass

        await wait(1)
        await submit_btn.click(timeout=3000)
        log("✅ Clicked submit button")

        # Wait for remix process to complete and URL to change to new project
        # The URL starts as /projects/XXX and will change to /projects/YYY after remix
        log("Waiting for remix to complete (can take up to 15 min)...")
        try:
            old_url = page.url
            old_project_id = re.search(r'/projects/([a-f0-9-]+)', old_url).group(1) if '/projects/' in old_url else None
            
            # Poll for URL change (page.wait_for_url won't work since pattern already matches)
            start_time = asyncio.get_event_loop().time()
            timeout_seconds = 900  # 15 minutes
            
            while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
                await wait(2000)
                new_url = page.url
                
                # Extract new project ID
                match = re.search(r'/projects/([a-f0-9-]+)', new_url)
                if match:
                    new_project_id = match.group(1)
                    if new_project_id != old_project_id:
                        log(f"✅ Remix complete! New project URL: {new_url}")
                        log(f"📂 Remixed Project ID: {new_project_id}")
                        project_id = new_project_id
                        break
            else:
                raise Exception(f"Remix did not redirect to new project after {timeout_seconds}s")
                
        except Exception as e:
            log(f"❌ Remix completion failed: {e}", "ERROR")
            raise
        
        # Wait for chat interface to load
        log("Waiting for chat interface...")
        await wait(5000)
        
        return project_id

    except Exception as e:
        log(f"❌ Remix failed: {e}", "ERROR")
        raise


async def send_prompt(page, prompt: str):
    """Send a prompt to chat."""
    log(f"Sending prompt: {prompt}")
    
    # Wait for chat interface
    chat_input = None
    selectors_to_try = [
        'div[contenteditable="true"][role="textbox"]',
        '[data-testid="chat-composer-editor"] [role="textbox"]',
    ]
    
    for selector in selectors_to_try:
        try:
            chat_input = page.locator(selector).first
            await chat_input.wait_for(state="visible", timeout=10000)
            log(f"✅ Chat interface loaded")
            break
        except:
            continue
    
    if not chat_input:
        raise Exception("Chat interface not found")
    
    # Type prompt
    await chat_input.click()
    await wait(500)
    await chat_input.fill(prompt)
    await wait(1000)
    
    # Click send - USE REGULAR CLICK (CSP blocks js_click)
    send_btn = page.locator('[data-testid="chat-input-send"]')
    
    # Wait for send button to be enabled
    try:
        await send_btn.wait_for(state="visible", timeout=5000)
        is_disabled = await send_btn.is_disabled()
        if is_disabled:
            log("⚠️  Send button disabled, waiting...")
            await wait(2000)
    except:
        pass
    
    # Click send button multiple times if needed
    for attempt in range(3):
        try:
            await send_btn.click(timeout=3000)
            log(f"✅ Clicked send button (attempt {attempt+1})")
            await wait(1000)
            
            # Verify prompt was sent by checking if input is empty
            input_text = await chat_input.text_content()
            if not input_text or len(input_text.strip()) == 0:
                log(f"✅ Sent prompt: {prompt}")
                break
            else:
                if attempt < 2:
                    log(f"⚠️  Input not cleared, retrying send...")
                    await wait(1000)
        except Exception as e:
            if attempt < 2:
                log(f"⚠️  Send click failed: {e}, retrying...")
                await wait(1000)
            else:
                # Try pressing Enter as fallback
                log("⚠️  Clicking send failed, trying Enter key...")
                await chat_input.press("Enter")
                await wait(1000)
                log(f"✅ Sent prompt via Enter: {prompt}")


async def test_subprocess_with_retry(page, browser, project_id: str, max_retries: int = 5):
    """Open preview tab and test subprocess with refresh retry."""
    
    preview_url = f"https://{project_id}.lovableproject.com"
    
    log(f"Opening preview tab: {preview_url}")
    
    # Get cookies from main page
    cookies = await page.context.cookies()
    log(f"  Copying {len(cookies)} cookies to preview tab")
    
    # Create new preview tab
    preview_page = await browser.new_page()
    await preview_page.context.add_cookies(cookies)
    
    # Try up to max_retries times
    for attempt in range(1, max_retries + 1):
        log(f"Attempt {attempt}/{max_retries}: Loading preview...")
        
        await preview_page.goto(preview_url, wait_until="load", timeout=60000)
        await wait(5000)
        log("✅ Preview loaded")
        
        # Wait for "lovable" console message (5 minutes)
        log("Waiting for 'lovable' console message (5 min timeout)...")
        
        console_messages = []
        lovable_found = False
        
        def on_console(msg):
            nonlocal lovable_found  # Must be first
            text = msg.text
            console_messages.append(text)
            if 'lovable' in text.lower():
                lovable_found = True
                log(f"✅ Found 'lovable' console message: {text[:100]}")
        
        preview_page.on("console", on_console)
        
        # Wait for page to be ready
        try:
            await preview_page.wait_for_load_state("networkidle", timeout=30000)
        except:
            pass
        
        # Wait up to 5 minutes for "lovable" message
        start_time = asyncio.get_event_loop().time()
        timeout = 300  # 5 minutes
        
        while not lovable_found and (asyncio.get_event_loop().time() - start_time) < timeout:
            await wait(2000)
        
        if lovable_found:
            log("✅ 'lovable' message detected!")
            break
        else:
            log(f"⚠️  'lovable' message NOT found in 5 minutes (attempt {attempt}/{max_retries})", "WARNING")
            if attempt < max_retries:
                log(f"🔄 Refreshing preview tab and retrying...")
                await wait(2000)
            else:
                log("❌ Max retries reached - subprocess might not be available", "ERROR")
                break
    
    # Test window.doc.run('git ') command (note the space after git)
    if lovable_found:
        log("Testing await doc.run('git ') command...")
        try:
            # Check if window.doc exists
            doc_exists = await preview_page.evaluate("typeof window.doc !== 'undefined'")
            if doc_exists:
                log("  ✅ window.doc exists!")
                
                # Try calling doc.run('git ') - NOTE THE SPACE
                # Must wrap in async function for await to work
                result = await preview_page.evaluate("""
                    (async () => {
                        return await window.doc.run('git ');
                    })()
                """)
                log(f"  ✅ await doc.run('git ') result: {str(result)[:200]}")
            else:
                log("  ⚠️ window.doc not found")
        except Exception as e:
            log(f"  ⚠️ Test error: {e}")
    
    return preview_page, lovable_found


async def keep_alive_both_tabs(page, preview_page, editor_url: str, preview_url: str):
    """Keep both tabs alive for 45-60 min with random human-like actions."""
    duration_minutes = random.randint(45, 60)
    duration_seconds = duration_minutes * 60
    
    log(f"🕐 Keeping both tabs alive for {duration_minutes} minutes with human actions...")
    
    start_time = time.time()
    action_count = 0
    
    while time.time() - start_time < duration_seconds:
        try:
            action_count += 1
            
            # Randomly choose which tab to act on
            target_page = random.choice([page, preview_page])
            tab_name = "editor" if target_page == page else "preview"
            
            # Random action
            action_type = random.choice([
                "mouse_move", "scroll", "click_random", "wait_longer"
            ])
            
            if action_type == "mouse_move":
                await target_page.mouse.move(
                    random.randint(100, 1000),
                    random.randint(100, 700)
                )
                log(f"🖱️  Action #{action_count}: Mouse move ({tab_name})")
            
            elif action_type == "scroll":
                await target_page.mouse.wheel(0, random.randint(-300, 300))
                log(f"📜 Action #{action_count}: Scroll ({tab_name})")
            
            elif action_type == "click_random":
                await target_page.mouse.click(
                    random.randint(200, 800),
                    random.randint(200, 600)
                )
                log(f"🖱️  Action #{action_count}: Random click ({tab_name})")
            
            elif action_type == "wait_longer":
                wait_time = random.randint(15, 45)
                log(f"💭 Action #{action_count}: Waiting {wait_time}s (simulating reading)")
                await asyncio.sleep(wait_time)
                continue
            
            # Random delay between actions (5-30 seconds)
            delay = random.randint(5, 30)
            await asyncio.sleep(delay)
        
        except Exception as e:
            log(f"⚠️  Action error: {e}", "WARNING")
            await asyncio.sleep(10)
    
    elapsed = (time.time() - start_time) / 60
    log(f"✅ Keep-alive complete: {elapsed:.1f} minutes, {action_count} actions")
    
    await preview_page.close()
    log("✅ Closed preview tab")


async def main(session_num: int, invite_link: str, headless: bool = False):
    """Main automation flow."""
    
    print("=" * 60)
    print("🚀 LOVABLE INVITE AUTOMATION")
    print("=" * 60)
    
    # Load session
    session_dir = SESSIONS_DIR / f"session-{session_num}"
    if not session_dir.exists():
        log(f"❌ Session {session_num} not found", "ERROR")
        sys.exit(1)
    
    with open(session_dir / "config.json") as f:
        config = json.load(f)
    
    with open(session_dir / "cookies.json") as f:
        session_cookies = json.load(f)
    
    email = config["email"]
    
    log(f"✅ Loaded session-{session_num}")
    log(f"📧 Email: {email}")
    log(f"🔗 Invite: {invite_link}")
    
    # Load real browser cookies
    real_cookies = []
    if REAL_COOKIES_PATH.exists():
        with open(REAL_COOKIES_PATH) as f:
            real_cookies = json.load(f)
        log(f"✅ Loaded {len(real_cookies)} real browser cookies")
    
    # Start browser
    async with InvisiblePlaywright() as browser:
        log("✅ Applied INVISIBLE-PLAYWRIGHT (passes ALL bot detection)")
        
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()
        
        # Add cookies
        if real_cookies:
            lovable_cookies = [c for c in real_cookies if 'lovable.dev' in c.get('domain', '')]
            if lovable_cookies:
                await context.add_cookies(lovable_cookies)
        
        await context.add_cookies(session_cookies)
        
        # 1. Accept invite and remix
        project_id = await accept_invite_and_remix(page, invite_link, email)
        project_url = page.url
        
        # 2. Send prompt
        await send_prompt(page, "1+1")
        
        # 3. Wait exactly 1 minute
        log("⏳ Waiting 1 minute before opening preview...")
        await asyncio.sleep(60)
        
        # 4. Open preview tab and test subprocess (with retry)
        preview_page, subprocess_found = await test_subprocess_with_retry(
            page, browser, project_id, max_retries=5
        )
        
        # 5. Keep both tabs alive
        preview_url = f"https://{project_id}.lovableproject.com"
        await keep_alive_both_tabs(page, preview_page, project_url, preview_url)
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        print(f"Session: {session_num} ({email})")
        print(f"Project: {project_url}")
        print(f"Subprocess found: {subprocess_found}")
        print("=" * 60)
        
        log("✅ AUTOMATION COMPLETE!")
        
        input("\nPress Enter to close browser...")
        await browser.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Lovable Invite Automation")
    parser.add_argument("--session", type=int, required=True, help="Session number to use")
    parser.add_argument("--invite", type=str, 
                       default="https://lovable.dev/projects/9a194661-e6c0-4aa4-a407-0af26bfa2092?magic_link=mc_86e4c4fe-35ec-4caa-961b-b79fe08acaa4",
                       help="Invite link (default: provided link)")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    
    args = parser.parse_args()
    
    asyncio.run(main(args.session, args.invite, args.headless))

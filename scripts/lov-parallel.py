#!/usr/bin/env python3
"""
Create TWO Lovable accounts in parallel using separate tabs.
Based on lov-test.py but runs 2 flows simultaneously.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

from patchright.async_api import (
    BrowserContext,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)
from patchright.async_api import async_playwright


TEMPMAIL_URL = "https://tempmailhub.org/"
LOVABLE_URL = "https://lovable.dev/"
RESET_SUBJECT = "Reset your password for Lovable"
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", re.IGNORECASE)

# Ad blocker patterns
AD_BLOCK_PATTERNS = (
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "google-analytics.com", "googletagmanager.com/gtag", "analytics.google.com",
    "adservice.google", "adroll.com", "outbrain.com", "taboola.com",
    "amazon-adsystem.com", "moatads.com", "scorecardresearch.com", "criteo.com",
    "teads.tv", "doubleverify.com", "yieldmo.com", "adnxs.com", "adsafeprotected.com",
    "adzerk.net", "pubmatic.com", "casalemedia.com", "openx.net", "rubiconproject.com",
)


class FlowError(RuntimeError):
    """Raised when a site does not reach the expected state."""


async def install_aggressive_ad_blocker(page: Page) -> None:
    """Aggressively block ALL ads, trackers, and popups - but allow TempMailHub to load.
    Also inject human-like browser fingerprinting."""
    
    # Block ad domains BUT allow TempMailHub itself
    def should_block(url: str) -> bool:
        lowered = url.lower()
        
        # NEVER block TempMailHub itself
        if "tempmailhub.org" in lowered:
            return False
        
        # Block ads, trackers, analytics
        if any(needle in lowered for needle in AD_BLOCK_PATTERNS):
            return True
        # Block common ad servers (but be careful not to block the main site)
        if any(ad in lowered for ad in ["/ads/", "/ad/", "advertisement"]):
            return True
        # Block crypto miners
        if any(miner in lowered for miner in ["coinhive", "crypto-loot", "jsecoin"]):
            return True
        return False

    async def handler(route):
        if should_block(route.request.url):
            await route.abort()
        else:
            await route.continue_()

    await page.route("**/*", handler)
    
    # Inject MAXIMUM human-like fingerprinting + ad blocking
    await page.add_init_script("""
        // === HUMAN-LIKE FINGERPRINTING ===
        // Override WebGL to look like real Windows GPU
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {
            if (param === 37445) return 'Intel Inc.'; // UNMASKED_VENDOR_WEBGL
            if (param === 37446) return 'Intel(R) UHD Graphics 630'; // UNMASKED_RENDERER_WEBGL
            return getParameter.call(this, param);
        };
        
        // Override navigator properties
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
        
        // Add real-looking plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                { name: 'PDF Viewer', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer' },
                { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer' },
                { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer' },
                { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer' }
            ]
        });
        
        // Battery API
        if (navigator.getBattery) {
            const originalGetBattery = navigator.getBattery;
            navigator.getBattery = function() {
                return originalGetBattery().then(battery => {
                    Object.defineProperties(battery, {
                        charging: { get: () => true },
                        chargingTime: { get: () => 0 },
                        dischargingTime: { get: () => Infinity },
                        level: { get: () => 1 }
                    });
                    return battery;
                });
            };
        }
        
        // Canvas fingerprinting - add subtle noise
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function() {
            const context = this.getContext('2d');
            if (context) {
                const imageData = context.getImageData(0, 0, this.width, this.height);
                for (let i = 0; i < imageData.data.length; i += 4) {
                    imageData.data[i] += Math.floor(Math.random() * 3) - 1;
                }
                context.putImageData(imageData, 0, 0);
            }
            return originalToDataURL.apply(this, arguments);
        };
        
        // === AD BLOCKING ===
        const style = document.createElement('style');
        style.textContent = `
            /* Hide ads */
            [class*="ad-"], [id*="ad-"], [class*="ads"], [id*="ads"],
            [class*="banner"], [id*="banner"], [class*="sponsor"],
            iframe[src*="ads"], iframe[src*="doubleclick"],
            /* Hide popups and overlays */
            [class*="popup"], [class*="modal"], [class*="overlay"],
            [role="dialog"]:not([aria-label*="Terms"]):not([aria-label*="Cookie"]),
            /* Hide specific annoying elements */
            .ad, .ads, .adsbygoogle, #ads, #ad-container,
            /* Make sure content is visible */
            body { overflow: visible !important; }
        `;
        document.head.appendChild(style);
        
        // Remove ad elements continuously
        setInterval(() => {
            document.querySelectorAll('[class*="ad-"], [id*="ad-"], [class*="popup"], iframe[src*="ads"]').forEach(el => {
                if (!el.closest('.email-content')) { // Don't remove email content
                    el.remove();
                }
            });
        }, 1000);
    """)


async def install_ad_blocker(page: Page) -> None:
    """Standard ad blocker + human fingerprinting for Lovable pages."""
    def should_block(url: str) -> bool:
        lowered = url.lower()
        return any(needle in lowered for needle in AD_BLOCK_PATTERNS)

    async def handler(route):
        if should_block(route.request.url):
            await route.abort()
        else:
            await route.continue_()

    await page.route("**/*", handler)
    
    # Also add human fingerprinting to Lovable
    await page.add_init_script("""
        // Override WebGL
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {
            if (param === 37445) return 'Intel Inc.';
            if (param === 37446) return 'Intel(R) UHD Graphics 630';
            return getParameter.call(this, param);
        };
        
        // Override navigator
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
    """)


async def body_text(page: Page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=3_000)
    except PlaywrightTimeoutError:
        return ""


async def wait_for_text(page: Page, text: str, timeout: float = 60) -> str:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        current = await body_text(page)
        if text.lower() in current.lower():
            return current
        await page.wait_for_timeout(500)
    raise FlowError(f"Timed out waiting for {text!r} on {page.url}")


async def wait_for_dashboard(page: Page, timeout: float = 45) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        current = await body_text(page)
        if "/dashboard" in page.url and "Dashboard" in current:
            return
        await page.wait_for_timeout(1_000)
    raise FlowError(f"Lovable did not reach the dashboard: {page.url}")


async def navigate(page: Page, url: str) -> None:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    except PlaywrightTimeoutError:
        pass


async def human_delay(min_ms: int = 500, max_ms: int = 1500):
    """Add random human-like delay."""
    import random
    delay = random.randint(min_ms, max_ms)
    await asyncio.sleep(delay / 1000)


async def click_exact(page: Page, text: str, timeout: float = 15) -> None:
    """Click with human-like behavior."""
    locator = page.get_by_role("button", name=text, exact=True)
    if await locator.count() == 0:
        locator = page.get_by_role("menuitem", name=text, exact=True)
    if await locator.count() == 0:
        locator = page.get_by_text(text, exact=True)
    if await locator.count() == 0:
        raise FlowError(f"Could not find clickable text {text!r} on {page.url}")
    
    # Add small delay before clicking (human-like)
    await human_delay(300, 800)
    
    # Move mouse to element first (more human-like)
    try:
        box = await locator.last.bounding_box()
        if box:
            await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            await human_delay(100, 300)
    except:
        pass
    
    await locator.last.click(timeout=timeout * 1_000, force=True)


async def dismiss_cookie_banner(page: Page) -> None:
    for label in ("Accept all", "OK", "Reject all"):
        button = page.get_by_role("button", name=label, exact=True)
        if await button.count() and await button.last.is_visible():
            await button.last.click(force=True)
            return


async def remove_tempmail_popup(page: Page) -> None:
    await page.evaluate(
        """() => {
          document.querySelectorAll('[role="dialog"][aria-modal="true"]')
            .forEach(node => node.remove());
        }"""
    )


async def create_temp_email(page: Page) -> str:
    """Create temp email - navigate only if not already on TempMailHub."""
    # Listen for popup windows and close them immediately
    context = page.context
    
    async def close_popup(popup):
        try:
            await popup.close()
            print("  🚫 Closed ad popup", file=sys.stderr)
        except:
            pass
    
    context.on("page", close_popup)
    
    # Block navigations away from TempMailHub (prevent redirects) - ONLY for this page
    async def block_redirects(route):
        url = route.request.url
        # Allow only TempMailHub
        if "tempmailhub.org" in url or url.startswith("data:") or url.startswith("blob:"):
            await route.continue_()
        else:
            print(f"  🚫 Blocked redirect to: {url[:80]}", file=sys.stderr)
            await route.abort()
    
    # Only navigate if we're not already on TempMailHub
    if "tempmailhub.org" not in page.url:
        print(f"  📍 Navigating to {TEMPMAIL_URL}", file=sys.stderr)
        
        # Install redirect blocker BEFORE navigation - ONLY on this page
        await page.route("**/*", block_redirects)
        
        # Navigate and wait for load
        await page.goto(TEMPMAIL_URL, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(5_000)  # Let page settle
    else:
        # Already on TempMailHub, install blocker now
        await page.route("**/*", block_redirects)
    
    # Debug: check actual URL
    print(f"  📍 Current URL: {page.url}", file=sys.stderr)
    
    # If not on TempMailHub, it redirected before we could block
    if "tempmailhub.org" not in page.url:
        raise FlowError(f"TempMailHub redirected before we could block: {page.url}")
    
    await remove_tempmail_popup(page)
    
    # Wait for the generate button to be visible
    try:
        await page.wait_for_selector('button[title="Generate new email"]', timeout=30_000)
    except PlaywrightTimeoutError:
        print("⚠️  Generate button not found, checking page content...", file=sys.stderr)
        text = await body_text(page)
        print(f"⚠️  Page content: {text[:200]}", file=sys.stderr)
        print(f"⚠️  Page URL: {page.url}", file=sys.stderr)
        
        # Check if page is blank - might need to wait more
        if not text.strip():
            print("  ⏳ Page is blank, waiting longer...", file=sys.stderr)
            await page.wait_for_timeout(10_000)
            try:
                await page.wait_for_selector('button[title="Generate new email"]', timeout=15_000)
                # Success! Continue
            except PlaywrightTimeoutError:
                # Try to save screenshot
                try:
                    await page.screenshot(path="/tmp/tempmail_missing_button.png")
                    print(f"⚠️  Saved screenshot to /tmp/tempmail_missing_button.png", file=sys.stderr)
                except:
                    pass
                raise FlowError("TempMailHub generate button not found after extended wait")
        else:
            # Try to save screenshot
            try:
                await page.screenshot(path="/tmp/tempmail_missing_button.png")
                print(f"⚠️  Saved screenshot to /tmp/tempmail_missing_button.png", file=sys.stderr)
            except:
                pass
            raise FlowError("TempMailHub generate button not found")

    generate = page.locator('button[title="Generate new email"]')
    await generate.click(force=True)
    await page.wait_for_timeout(3_000)
    await remove_tempmail_popup(page)

    # Try to find email in page text
    deadline = asyncio.get_running_loop().time() + 30
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        matches = EMAIL_RE.findall(text)
        if matches:
            print(f"✓ Generated email: {matches[0]}", file=sys.stderr)
            # Remove popup listener
            try:
                context.remove_listener("page", close_popup)
            except:
                pass
            # Keep redirect blocker active for TempMailHub page
            return matches[0]
        await page.wait_for_timeout(1_000)
    
    # Debug: save screenshot and page content
    try:
        await page.screenshot(path="/tmp/tempmail_fail.png")
        print(f"⚠️  Saved screenshot to /tmp/tempmail_fail.png", file=sys.stderr)
        print(f"⚠️  Page text: {text[:500]}", file=sys.stderr)
    except:
        pass
    
    raise FlowError("TempMailHub did not display an email address")


async def create_unused_temp_email(page: Page, used: set[str]) -> str:
    for _ in range(3):
        email = await create_temp_email(page)
        if email not in used:
            return email
        await page.wait_for_timeout(1_000)
    raise FlowError("TempMailHub kept returning the same temporary address")


async def wait_for_lovable_ready(page: Page, timeout: float = 75) -> None:
    """Wait for Lovable to be ready. Handle errors WITHOUT reloading page."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        if "Performing security verification" in text:
            await page.wait_for_timeout(2_500)
            continue
        # If there's an error, just wait - don't reload and lose cookies
        if "We hit a snag" in text:
            print("⚠️  Lovable showing error, waiting...", file=sys.stderr)
            await page.wait_for_timeout(5_000)
            continue
        if "Log in" in text or ("/dashboard" in page.url and "Dashboard" in text):
            return
        await page.wait_for_timeout(1_000)
    raise FlowError("Lovable did not finish loading or its security check")


async def sign_out_if_needed(page: Page) -> None:
    """Sign out from Lovable if already logged in.
    DO NOT RELOAD - just handle sign out without breaking session."""
    account = page.locator('button[aria-label="Account menu"]')
    
    # Check if we're on dashboard and account menu is not visible
    if "/dashboard" in page.url and await account.count() == 0:
        # Wait a bit for menu to appear, but don't reload
        await page.wait_for_timeout(2_500)
    
    if "/dashboard" in page.url:
        try:
            await account.last.wait_for(state="visible", timeout=20_000)
        except PlaywrightTimeoutError as exc:
            raise FlowError("Lovable dashboard did not render its account menu") from exc
    
    if await account.count() == 0 or not await account.last.is_visible():
        return

    sign_out = page.get_by_role("menuitem", name="Sign out", exact=True)
    for _menu_try in range(3):
        if await sign_out.count() and await sign_out.last.is_visible():
            await sign_out.last.click(force=True)
            break
        await account.last.evaluate("node => node.click()")
        await page.wait_for_timeout(500)
    else:
        raise FlowError("Lovable account menu did not show Sign out")
    
    deadline = asyncio.get_running_loop().time() + 30
    while asyncio.get_running_loop().time() < deadline:
        if "/dashboard" not in page.url and "Log in" in await body_text(page):
            return
        await page.wait_for_timeout(500)
    raise FlowError("Lovable did not finish signing out")


async def human_type(locator, text: str):
    """Type text with human-like delays between keystrokes."""
    import random
    await locator.click()
    await human_delay(200, 500)
    
    for char in text:
        await locator.type(char, delay=random.randint(50, 150))
    
    await human_delay(300, 600)


async def request_reset(page: Page, email: str) -> None:
    await navigate(page, LOVABLE_URL)
    await wait_for_lovable_ready(page)
    await dismiss_cookie_banner(page)
    await sign_out_if_needed(page)

    if "/dashboard" in page.url:
        await navigate(page, LOVABLE_URL)
        await wait_for_lovable_ready(page)

    await click_exact(page, "Log in")
    email_input = page.locator('input[type="email"]').last
    for _login_try in range(2):
        try:
            await email_input.wait_for(state="visible", timeout=15_000)
            break
        except PlaywrightTimeoutError:
            if _login_try == 1:
                raise FlowError("Lovable login modal did not render its email field")
            await click_exact(page, "Log in")
    
    # Type email with human-like behavior
    await human_type(email_input, email)
    await click_exact(page, "Continue")
    
    await page.locator('input[type="password"]').wait_for(timeout=20_000)
    await click_exact(page, "Forgot password?")

    reset_email = page.locator('input[placeholder="Enter your email address"]')
    if await reset_email.count() == 0:
        reset_email = page.locator('input[type="email"]')
    current_email = (await reset_email.last.input_value()).strip().lower()
    if current_email != email.lower():
        await click_exact(page, "Use a different email")
        reset_email = page.locator('input[placeholder="Enter your email address"]')
        await human_type(reset_email.last, email)
    await click_exact(page, "Send reset link")
    await wait_for_text(page, "Check your email", timeout=20)


async def read_reset_link(
    page: Page,
    timeout: float = 180,
    ignored_items: Optional[set[str]] = None,
) -> str:
    """Read reset link from mailbox. Handle IMAP errors by refreshing."""
    ignored_items = ignored_items or set()
    deadline = asyncio.get_running_loop().time() + timeout
    
    while asyncio.get_running_loop().time() < deadline:
        await remove_tempmail_popup(page)
        current_text = await body_text(page)
        
        # Check for IMAP error and refresh
        if "IMAP" in current_text and ("failed" in current_text.lower() or "error" in current_text.lower()):
            print("  ⚠️  IMAP error while reading messages, refreshing...", file=sys.stderr)
            refresh = page.locator('button[title="Refresh inbox"]')
            if await refresh.count():
                await refresh.click(force=True)
            await page.wait_for_timeout(5_000)
            continue
        
        # Look for reset email
        email_item = page.locator("li.email-item").filter(has_text=RESET_SUBJECT)
        for index in range(await email_item.count()):
            candidate = email_item.nth(index)
            if (await candidate.inner_text()).strip() in ignored_items:
                continue
            await candidate.click(force=True)
            await page.wait_for_timeout(2_000)
            
            link = page.locator('a[href*="resetPassword"]').first
            if await link.count():
                href = await link.get_attribute("href")
                if href:
                    print("  ✅ Found reset link!", file=sys.stderr)
                    return href

        retry = page.get_by_text("Try Again", exact=True)
        if await retry.count() and "Try Again" in current_text:
            await retry.last.click(force=True)
        elif "Fetching messages" in current_text:
            await page.wait_for_timeout(6_000)
            continue
        else:
            refresh = page.locator('button[title="Refresh inbox"]')
            if await refresh.count():
                await refresh.click(force=True)
        await page.wait_for_timeout(6_000)

    raise FlowError(f"Timed out waiting for {RESET_SUBJECT!r} in TempMailHub")


async def wait_until_mailbox_ready(page: Page, max_attempts: int = 10) -> None:
    """Keep refreshing until IMAP error disappears."""
    print("📧 Waiting for mailbox to be ready (handling IMAP errors)...", file=sys.stderr)
    
    for attempt in range(max_attempts):
        await remove_tempmail_popup(page)
        text = await body_text(page)
        
        # Check if IMAP error is present
        if "IMAP" in text and ("failed" in text.lower() or "error" in text.lower()):
            print(f"  ⚠️  IMAP error detected (attempt {attempt + 1}/{max_attempts}), refreshing...", file=sys.stderr)
            
            # Click refresh button
            refresh = page.locator('button[title="Refresh inbox"]')
            if await refresh.count():
                await refresh.click(force=True)
                await page.wait_for_timeout(5_000)
            else:
                # Try generic refresh button
                await page.reload()
                await page.wait_for_timeout(5_000)
            continue
        
        # Check if mailbox is ready (no errors)
        if "Fetching messages" not in text and "IMAP" not in text:
            print("  ✅ Mailbox ready!", file=sys.stderr)
            return
        
        await page.wait_for_timeout(3_000)
    
    raise FlowError("Mailbox still has IMAP errors after multiple refresh attempts")


async def existing_reset_items(page: Page, timeout: float = 45) -> set[str]:
    """Wait for the current mailbox state before requesting a new message.
    DO NOT REFRESH - keep session alive. Handle IMAP errors by refreshing."""
    
    # First, wait until IMAP errors are gone
    await wait_until_mailbox_ready(page)
    
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        await remove_tempmail_popup(page)
        text = await body_text(page)
        
        # Check for IMAP error again
        if "IMAP" in text and ("failed" in text.lower() or "error" in text.lower()):
            print("  ⚠️  IMAP error reappeared, refreshing...", file=sys.stderr)
            refresh = page.locator('button[title="Refresh inbox"]')
            if await refresh.count():
                await refresh.click(force=True)
            await page.wait_for_timeout(5_000)
            continue
        
        # Don't refresh page - just handle UI states
        if "Fetching messages" in text:
            await page.wait_for_timeout(4_000)
            continue
        
        # Only click Try Again button if present, don't reload page
        retry = page.get_by_text("Try Again", exact=True)
        if await retry.count() and "Try Again" in text:
            await retry.last.click(force=True)
            await page.wait_for_timeout(6_000)
            continue
        
        # Return existing items without refreshing
        return set(
            await page.locator("li.email-item")
            .filter(has_text=RESET_SUBJECT)
            .all_inner_texts()
        )
    raise FlowError("TempMailHub inbox did not become ready before the reset request")


async def set_password_and_verify(page: Page, reset_url: str, password: str) -> None:
    await navigate(page, reset_url)
    new_password = page.locator('input[name="newPassword"]')
    confirm_password = page.locator('input[name="confirmPassword"]')
    await new_password.wait_for(timeout=30_000)
    await new_password.fill(password)
    await confirm_password.fill(password)
    await click_exact(page, "Reset Password")
    deadline = asyncio.get_running_loop().time() + 45
    while asyncio.get_running_loop().time() < deadline:
        text = await body_text(page)
        if "Your password has been updated" in text:
            break
        if "/dashboard" in page.url and "Dashboard" in text:
            return
        if "Password must contain" in text:
            raise FlowError("Lovable rejected the generated password requirements")
        await page.wait_for_timeout(500)
    else:
        raise FlowError("Lovable did not confirm the password reset")
    await wait_for_dashboard(page, timeout=45)


async def get_page(context: BrowserContext, host: str) -> Page:
    """Get existing page or create new one - reuse tabs instead of duplicating."""
    for page in context.pages:
        if host in page.url:
            return page
        if page.url in ("", "about:blank"):
            return page
    return await context.new_page()


async def run_single_flow_with_own_tabs(context: BrowserContext, flow_id: int) -> dict[str, object]:
    """Run a single Lovable account creation with its own dedicated tabs."""
    print(f"[Flow {flow_id}] Starting with dedicated tabs...", file=sys.stderr)
    
    # Each flow gets its own tabs
    temp_page = await context.new_page()
    lovable_page = await context.new_page()

    last_error: Optional[Exception] = None
    used_emails: set[str] = set()
    
    for attempt in range(1, 4):
        try:
            print(f"[Flow {flow_id}] Attempt {attempt}/3: generating temporary address", file=sys.stderr)
            email = await create_unused_temp_email(temp_page, used_emails)
            used_emails.add(email)
            password = email if re.search(r"\d", email) else f"{email}1"
            
            old_reset_items = await existing_reset_items(temp_page)
            print(f"[Flow {flow_id}] Attempt {attempt}/3: requesting reset for {email}", file=sys.stderr)
            await request_reset(lovable_page, email)
            
            reset_url = await read_reset_link(temp_page, timeout=180, ignored_items=old_reset_items)
            print(f"[Flow {flow_id}] Attempt {attempt}/3: reset email received", file=sys.stderr)
            
            await set_password_and_verify(lovable_page, reset_url, password)
            print(f"[Flow {flow_id}] Attempt {attempt}/3: dashboard verified ✅", file=sys.stderr)
            break
        except Exception as exc:
            last_error = exc
            print(f"[Flow {flow_id}] Attempt {attempt}/3 failed: {exc}", file=sys.stderr)
    else:
        raise FlowError(f"[Flow {flow_id}] All attempts failed: {last_error}") from last_error

    dashboard_text = await body_text(lovable_page)
    account_menu = lovable_page.locator('button[aria-label="Account menu"]')
    try:
        await account_menu.wait_for(state="visible", timeout=20_000)
    except PlaywrightTimeoutError as exc:
        raise FlowError(f"[Flow {flow_id}] Dashboard account menu did not render") from exc
    
    if "/dashboard" not in lovable_page.url or "Dashboard" not in dashboard_text:
        raise FlowError(f"[Flow {flow_id}] Dashboard loaded but account not verified")

    return {
        "flow_id": flow_id,
        "verified": True,
        "email": email,
        "password": password,
        "dashboard_url": lovable_page.url,
        "tempmail_url": temp_page.url,
    }


async def load_cookies_from_file(context: BrowserContext, cookie_file: str) -> None:
    """Load cookies from Netscape format file."""
    import os
    
    if not os.path.exists(cookie_file):
        print(f"⚠️  Cookie file not found: {cookie_file}", file=sys.stderr)
        return
    
    print(f"🍪 Loading cookies from {cookie_file}...", file=sys.stderr)
    
    cookies = []
    with open(cookie_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split('\t')
            if len(parts) < 7:
                continue
            
            domain, _, path, secure, expires, name, value = parts[:7]
            
            cookie = {
                'name': name,
                'value': value,
                'domain': domain,
                'path': path,
                'expires': int(float(expires)) if expires != '0' else -1,
                'httpOnly': False,
                'secure': secure == 'TRUE',
                'sameSite': 'Lax'
            }
            cookies.append(cookie)
    
    if cookies:
        await context.add_cookies(cookies)
        print(f"✅ Loaded {len(cookies)} cookies", file=sys.stderr)


def check_current_ip() -> str:
    """Check current public IP address."""
    import urllib.request
    try:
        with urllib.request.urlopen('https://api.ipify.org', timeout=10) as response:
            return response.read().decode('utf-8')
    except Exception:
        return "unknown"


def rotate_warp_ip() -> bool:
    """Rotate WARP IP by updating wgcf account."""
    import subprocess
    import time
    from pathlib import Path
    
    print("🔄 Rotating WARP IP...", file=sys.stderr)
    
    old_ip = check_current_ip()
    print(f"  Current IP: {old_ip}", file=sys.stderr)
    
    try:
        # Run wgcf update in home directory where config exists
        result = subprocess.run(
            ["wgcf", "update"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path.home())
        )
        
        if result.returncode != 0:
            print(f"  ⚠️ wgcf update failed: {result.stderr.strip()}", file=sys.stderr)
            return False
        
        # Regenerate profile
        result = subprocess.run(
            ["wgcf", "generate"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path.home())
        )
        
        if result.returncode != 0:
            print(f"  ⚠️ wgcf generate failed: {result.stderr.strip()}", file=sys.stderr)
            return False
        
        print("  ✅ New WARP config generated", file=sys.stderr)
        return True
        
    except Exception as e:
        print(f"  ⚠️ WARP rotation failed: {e}", file=sys.stderr)
        return False


def start_warp() -> bool:
    """Start WireGuard WARP interface."""
    import subprocess
    import time
    
    print("🌐 Starting WARP...", file=sys.stderr)
    
    try:
        # Check if already running
        result = subprocess.run(["sudo", "wg", "show", "wgcf"], 
                              capture_output=True, timeout=5)
        if result.returncode == 0:
            print("  ℹ️  WARP already running, restarting...", file=sys.stderr)
            subprocess.run(["sudo", "wg-quick", "down", "wgcf"], 
                         capture_output=True, timeout=10)
            time.sleep(1)
        
        # Start WireGuard
        result = subprocess.run(
            ["sudo", "wg-quick", "up", "wgcf"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            print(f"  ⚠️ Failed to start WARP: {result.stderr.strip()}", file=sys.stderr)
            return False
        
        time.sleep(2)
        
        new_ip = check_current_ip()
        print(f"  ✅ WARP started - IP: {new_ip}", file=sys.stderr)
        return True
        
    except Exception as e:
        print(f"  ⚠️ WARP start failed: {e}", file=sys.stderr)
        return False


def stop_warp() -> bool:
    """Stop WireGuard WARP interface."""
    import subprocess
    
    print("🛑 Stopping WARP...", file=sys.stderr)
    
    try:
        result = subprocess.run(
            ["sudo", "wg-quick", "down", "wgcf"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print("  ✅ WARP stopped", file=sys.stderr)
        else:
            print("  ℹ️  WARP already stopped", file=sys.stderr)
        
        return True
        
    except Exception as e:
        print(f"  ⚠️ Failed to stop WARP: {e}", file=sys.stderr)
        return False


async def run_sequential_in_two_tabs(context: BrowserContext, num_accounts: int = 2, use_warp: bool = False) -> dict:
    """Create multiple Lovable accounts using ONLY 2 tabs (sequential execution)."""
    print(f"🚀 Creating {num_accounts} Lovable accounts using 2 tabs (sequential)...", file=sys.stderr)
    print(f"📊 Opening 2 tabs total: 1 TempMail + 1 Lovable", file=sys.stderr)
    
    warp_started = False
    
    try:
        # Step 1: WARP setup (if enabled)
        if use_warp:
            print("\n" + "="*60, file=sys.stderr)
            print("STEP 1: Setting up WARP", file=sys.stderr)
            print("="*60 + "\n", file=sys.stderr)
            if rotate_warp_ip():
                warp_started = start_warp()
                if not warp_started:
                    print("⚠️  WARP failed to start, continuing with direct connection", file=sys.stderr)
            else:
                print("⚠️  WARP rotation failed, using direct connection", file=sys.stderr)
        
        # Step 2: Load cookies from file
        print("\n" + "="*60, file=sys.stderr)
        print(f"STEP 2: Loading cookies from file", file=sys.stderr)
        print("="*60 + "\n", file=sys.stderr)
        cookie_file = "/home/alae/Downloads/tu-cookies.txt"
        await load_cookies_from_file(context, cookie_file)
        
        # Step 3: Create tabs and install ad blockers
        print("\n" + "="*60, file=sys.stderr)
        print("STEP 3: Creating browser tabs", file=sys.stderr)
        print("="*60 + "\n", file=sys.stderr)
        temp_page = await context.new_page()
        lovable_page = await context.new_page()
        
        # Install AGGRESSIVE ad blocker on TempMail (full of ads)
        print("🛡️  Installing aggressive ad blocker on TempMail...", file=sys.stderr)
        await install_aggressive_ad_blocker(temp_page)
        
        # Install standard ad blocker on Lovable
        print("🛡️  Installing ad blocker on Lovable...", file=sys.stderr)
        await install_ad_blocker(lovable_page)
        
        # Step 4: Verify cookie session by navigating to TempMail
        print("\n" + "="*60, file=sys.stderr)
        print("STEP 4: Verifying cookie session", file=sys.stderr)
        print("="*60 + "\n", file=sys.stderr)
        print("🌐 Navigating to TempMailHub to verify session...", file=sys.stderr)
        await temp_page.goto(TEMPMAIL_URL, wait_until="domcontentloaded", timeout=60_000)
        await temp_page.wait_for_timeout(3_000)
        print(f"✅ Session verified - Current URL: {temp_page.url}", file=sys.stderr)
        
        # Step 5: Start account creation
        print("\n" + "="*60, file=sys.stderr)
        print("STEP 5: Starting account creation", file=sys.stderr)
        print("="*60 + "\n", file=sys.stderr)
        
        results = {"successes": [], "failures": []}
        
        for account_num in range(1, num_accounts + 1):
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"Creating Account {account_num}/{num_accounts}", file=sys.stderr)
            print(f"{'='*60}\n", file=sys.stderr)
            
            last_error: Optional[Exception] = None
            used_emails: set[str] = set()
            
            for attempt in range(1, 4):
                try:
                    print(f"[Account {account_num}] Attempt {attempt}/3: generating temporary address", file=sys.stderr)
                    email = await create_unused_temp_email(temp_page, used_emails)
                    used_emails.add(email)
                    password = email if re.search(r"\d", email) else f"{email}1"
                    
                    old_reset_items = await existing_reset_items(temp_page)
                    print(f"[Account {account_num}] Attempt {attempt}/3: requesting reset for {email}", file=sys.stderr)
                    await request_reset(lovable_page, email)
                    
                    reset_url = await read_reset_link(temp_page, timeout=180, ignored_items=old_reset_items)
                    print(f"[Account {account_num}] Attempt {attempt}/3: reset email received", file=sys.stderr)
                    
                    await set_password_and_verify(lovable_page, reset_url, password)
                    print(f"[Account {account_num}] Attempt {attempt}/3: dashboard verified ✅", file=sys.stderr)
                    
                    dashboard_text = await body_text(lovable_page)
                    account_menu = lovable_page.locator('button[aria-label="Account menu"]')
                    await account_menu.wait_for(state="visible", timeout=20_000)
                
                result = {
                    "account_number": account_num,
                    "verified": True,
                    "email": email,
                    "password": password,
                    "dashboard_url": lovable_page.url,
                }
                results["successes"].append(result)
                print(f"✅ [Account {account_num}] SUCCESS: {email}", file=sys.stderr)
                
                # Rotate WARP IP before next account (except for last one)
                if use_warp and warp_started and account_num < num_accounts:
                    print(f"\n🔄 Rotating IP for next account...", file=sys.stderr)
                    if rotate_warp_ip():
                        # Restart WARP with new config
                        stop_warp()
                        import time
                        time.sleep(1)
                        start_warp()
                
                break
                
            except Exception as exc:
                last_error = exc
                print(f"[Account {account_num}] Attempt {attempt}/3 failed: {exc}", file=sys.stderr)
                else:
                    results["failures"].append({"account_number": account_num, "error": str(last_error)})
                    print(f"❌ [Account {account_num}] FAILED after all attempts", file=sys.stderr)
    
    finally:
        # Always stop WARP after script finishes to restore normal network
        if warp_started:
            stop_warp()
    
    return results
    
    for attempt in range(1, 4):
        try:
            print(f"[Flow {flow_id}] Attempt {attempt}/3: generating temporary address", file=sys.stderr)
            email = await create_unused_temp_email(temp_page, used_emails)
            used_emails.add(email)
            password = email if re.search(r"\d", email) else f"{email}1"
            
            old_reset_items = await existing_reset_items(temp_page)
            print(f"[Flow {flow_id}] Attempt {attempt}/3: requesting reset for {email}", file=sys.stderr)
            await request_reset(lovable_page, email)
            
            reset_url = await read_reset_link(temp_page, timeout=75, ignored_items=old_reset_items)
            print(f"[Flow {flow_id}] Attempt {attempt}/3: reset email received", file=sys.stderr)
            
            await set_password_and_verify(lovable_page, reset_url, password)
            print(f"[Flow {flow_id}] Attempt {attempt}/3: dashboard verified ✅", file=sys.stderr)
            break
        except Exception as exc:
            last_error = exc
            print(f"[Flow {flow_id}] Attempt {attempt}/3 failed: {exc}", file=sys.stderr)
    else:
        raise FlowError(f"[Flow {flow_id}] All attempts failed: {last_error}") from last_error

    dashboard_text = await body_text(lovable_page)
    account_menu = lovable_page.locator('button[aria-label="Account menu"]')
    try:
        await account_menu.wait_for(state="visible", timeout=20_000)
    except PlaywrightTimeoutError as exc:
        raise FlowError(f"[Flow {flow_id}] Dashboard account menu did not render") from exc
    
    if "/dashboard" not in lovable_page.url or "Dashboard" not in dashboard_text:
        raise FlowError(f"[Flow {flow_id}] Dashboard loaded but account not verified")

    return {
        "flow_id": flow_id,
        "verified": True,
        "email": email,
        "password": password,
        "dashboard_url": lovable_page.url,
        "tempmail_url": temp_page.url,
    }


async def launch_local_context(playwright, args: argparse.Namespace) -> BrowserContext:
    """Launch browser with MAXIMUM human-like fingerprinting and WARP proxy."""
    profile_dir = Path(args.profile_dir).expanduser().resolve()
    
    # WARP SOCKS5 proxy configuration (only affects this browser)
    proxy_config = {
        "server": "socks5://127.0.0.1:40000",  # WARP default SOCKS5 proxy
    }
    
    # Maximum human-like options
    options = {
        "user_data_dir": str(profile_dir),
        "headless": args.headless,
        "proxy": proxy_config,  # WARP proxy - only affects this browser!
        "viewport": {"width": 1920, "height": 1080},  # Most common desktop resolution
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "permissions": ["geolocation", "notifications"],
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "device_scale_factor": 1,
        "has_touch": False,
        "color_scheme": "light",
        "reduced_motion": "no-preference",
        "forced_colors": "none",
        # Accept language header
        "extra_http_headers": {
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        },
    }
    
    if args.browser_path:
        options["executable_path"] = args.browser_path
        return await playwright.chromium.launch_persistent_context(**options)

    try:
        # Try Chrome first (looks more legitimate)
        return await playwright.chromium.launch_persistent_context(channel="chrome", **options)
    except PlaywrightError:
        try:
            # Fall back to Chromium with channel specified for extension support
            return await playwright.chromium.launch_persistent_context(channel="chromium", **options)
        except PlaywrightError:
            try:
                # Last resort: default chromium
                return await playwright.chromium.launch_persistent_context(**options)
            except PlaywrightError as exc:
                raise FlowError(
                    "No usable browser found. Install Chrome or run 'python -m playwright install chromium'"
                ) from exc


async def run(args: argparse.Namespace) -> dict:
    async with async_playwright() as playwright:
        owned_context = not args.cdp_url
        if args.cdp_url:
            browser = await playwright.chromium.connect_over_cdp(args.cdp_url, timeout=60_000)
            if not browser.contexts:
                raise FlowError("The connected browser has no browser context")
            context = browser.contexts[0]
        else:
            context = await launch_local_context(playwright, args)

        # Create multiple accounts using ONLY 2 tabs (sequential)
        result = await run_sequential_in_two_tabs(context, num_accounts=args.num_flows, use_warp=args.warp)
        
        print("\n" + "="*60)
        print(json.dumps(result, indent=2))
        print("="*60)
        
        if owned_context and args.keep_browser_open:
            print("\nBrowser left open. Press Ctrl+C to close it.", file=sys.stderr)
            try:
                while True:
                    await asyncio.sleep(3_600)
            except (asyncio.CancelledError, KeyboardInterrupt):
                pass
        
        if owned_context and not args.keep_browser_open:
            await context.close()
        
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--num-flows",
        type=int,
        default=2,
        help="Number of parallel Lovable accounts to create (default: 2)",
    )
    parser.add_argument(
        "--cdp-url",
        default=os.environ.get("BU_CDP_WS"),
        help="Optional browser CDP WebSocket URL",
    )
    parser.add_argument(
        "--profile-dir",
        default=str(Path.home() / ".lovable-parallel-profile"),
        help="Browser profile directory",
    )
    parser.add_argument(
        "--browser-path",
        help="Optional path to Chrome/Chromium executable",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without visible window",
    )
    parser.add_argument(
        "--keep-browser-open",
        action="store_true",
        default=True,
        help="Keep browser open after completion (default)",
    )
    parser.add_argument(
        "--close-browser",
        dest="keep_browser_open",
        action="store_false",
        help="Close browser after completion",
    )
    parser.add_argument(
        "--warp",
        action="store_true",
        help="Use WARP VPN (WireGuard) for IP rotation between accounts",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        asyncio.run(run(args))
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"Automation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

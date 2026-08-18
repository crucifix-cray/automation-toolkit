# Insert this into sign_in_to_railway() after filling email

# FAST POLL BUTTON - Check button state every 500ms and click IMMEDIATELY when enabled
print("🔍 Checking for Cloudflare Turnstile...")
await page.wait_for_timeout(2000)

# Get button reference
continue_btn = page.get_by_role("button", name="Continue with Email", exact=True)

# Check for Turnstile
turnstile_exists = False
try:
    turnstile_iframe = page.locator('iframe[src*="challenges.cloudflare.com"]')
    if await turnstile_iframe.count() > 0:
        turnstile_exists = True
        print("✓ Found Turnstile iframe")
except:
    pass

if not turnstile_exists:
    try:
        has_turnstile = await page.evaluate('''() => {
            const input = document.querySelector('input[name="cf-turnstile-response"]');
            const container = input?.parentElement?.parentElement;
            return container && container.offsetHeight > 0;
        }''')
        if has_turnstile:
            turnstile_exists = True
            print("✓ Found Turnstile widget")
    except:
        pass

# If Turnstile exists, try auto-solve then FAST POLL button
if turnstile_exists:
    print("✓ Turnstile detected")
    
    # Try auto-solver if available
    if CAPTCHA_SOLVER_AVAILABLE:
        print("🤖 Attempting auto-solve...")
        try:
            async with ClickSolver(
                framework=FrameworkType.PATCHRIGHT,
                page=page,
                max_attempts=1,
                attempt_delay=2
            ) as solver:
                await solver.solve_captcha(
                    captcha_container=page,
                    captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE
                )
            print("✅ Auto-solver completed")
        except Exception as e:
            print(f"⚠️  Auto-solver failed: {str(e)[:60]}")
    
    # CRITICAL: Fast poll button state - check every 500ms
    print("⏳ Fast polling button (every 0.5s for 60s)...")
    import asyncio
    deadline = asyncio.get_running_loop().time() + 60
    
    while asyncio.get_running_loop().time() < deadline:
        try:
            # Check if button enabled
            is_enabled = await continue_btn.is_enabled(timeout=500)
            if is_enabled:
                print("✅ BUTTON ENABLED! Clicking NOW...")
                try:
                    await continue_btn.click(timeout=3000)
                    print("✅ Clicked!")
                    break
                except Exception as e:
                    print(f"⚠️  Click failed: {e}")
                    # Try force click
                    await continue_btn.click(force=True, timeout=3000)
                    print("✅ Force clicked!")
                    break
        except Exception:
            # Not enabled yet, keep polling
            await page.wait_for_timeout(500)
            continue
    else:
        # Timeout
        print(f"❌ Button never enabled after 60s")
        token_val = await page.evaluate('''() => {
            const input = document.querySelector('input[name="cf-turnstile-response"]');
            return input ? input.value.length : 0;
        }''')
        print(f"⚠️  Turnstile token length: {token_val}")
        screenshot_path = str(profile_dir / "turnstile_timeout.png")
        await page.screenshot(path=screenshot_path)
        print(f"⚠️  Screenshot: {screenshot_path}")
        raise RuntimeError("Turnstile not solved - button still disabled after 60s")
else:
    # No Turnstile, click immediately
    print("✓ No Turnstile, clicking button immediately")
    await continue_btn.click(timeout=10000)
    print("✅ Clicked!")

await wait_for_cloudflare(page, "Railway sign-in")

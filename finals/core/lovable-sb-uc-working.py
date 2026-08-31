#!/usr/bin/env python3
"""
Lovable.dev automation using SeleniumBase UC Mode
WORKING VERSION - Uses Driver instead of SB context manager
"""
import sys
import random

def main():
    from seleniumbase import Driver
    
    # Generate email
    base_names = ["yorhun", "alacat", "yavash", "balat", "mansur", "kurtaran"]
    email = f"{random.choice(base_names)}{random.randint(1,999)}@gmail.com"
    password = f"{email.split('@')[0]}KO"
    print(f"✅ Email: {email}", file=sys.stderr)
    
    # Check WARP
    proxy_arg = None
    try:
        import os, subprocess
        if os.environ.get("PROXY_PORT") == "40000":
            result = subprocess.run(
                ["curl", "--socks5", "127.0.0.1:40000", "https://cloudflare.com/cdn-cgi/trace", "--max-time", "10"],
                capture_output=True, text=True, timeout=12
            )
            if result.returncode == 0 and "warp=on" in result.stdout:
                proxy_arg = "socks5://127.0.0.1:40000"
                print(f"✅ Using WARP: {proxy_arg}", file=sys.stderr)
    except:
        pass
    
    # Launch UC Mode browser
    print("🚀 Launching SeleniumBase UC Mode...", file=sys.stderr)
    driver = Driver(
        uc=True,
        incognito=True,
        proxy=proxy_arg if proxy_arg else None
    )
    
    try:
        url = "https://lovable.dev/signup"
        print(f"🌐 Opening {url}...", file=sys.stderr)
        driver.uc_open_with_reconnect(url, reconnect_time=4)
        driver.sleep(2)
        
        # Fill email
        print(f"📧 Filling email...", file=sys.stderr)
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        email_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"]'))
        )
        email_field.clear()
        email_field.send_keys(email)
        driver.sleep(1)
        
        print("  ⏳ Waiting for page to be ready...", file=sys.stderr)
        driver.sleep(2)
        
        # Take screenshot before clicking
        try:
            driver.save_screenshot("/tmp/before-continue.png")
            print("  📸 Screenshot: /tmp/before-continue.png", file=sys.stderr)
        except:
            pass
        
        # Click Continue using uc_click with MORE SPECIFIC selector
        print("🖱️  Clicking Continue button...", file=sys.stderr)
        # Wait for Continue button to be ready and click it
        try:
            # Find the submit button after email field
            continue_selector = 'button[type="submit"]'
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, continue_selector))
            )
            driver.uc_click(continue_selector, by="css selector", reconnect_time=2)
            print("  ✅ Continue clicked", file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️  Continue click error: {e}", file=sys.stderr)
            # Fallback: try finding button with text
            try:
                driver.execute_script("""
                    const buttons = document.querySelectorAll('button');
                    for (let btn of buttons) {
                        if (btn.textContent.includes('Continue') && !btn.textContent.includes('Google')) {
                            btn.click();
                            break;
                        }
                    }
                """)
                print("  ✅ Continue clicked (JS fallback)", file=sys.stderr)
            except:
                pass
        
        # Wait longer for navigation and check what happened
        print("  ⏳ Waiting for navigation (15s)...", file=sys.stderr)
        driver.sleep(15)
        
        # Take screenshot after clicking
        try:
            driver.save_screenshot("/tmp/after-continue.png")
            print("  📸 Screenshot: /tmp/after-continue.png", file=sys.stderr)
        except:
            pass
        
        # Check current URL
        current = driver.current_url
        print(f"  📍 Current URL: {current}", file=sys.stderr)
        
        # Fill password - wait for it
        print("🔐 Filling password...", file=sys.stderr)
        pwd_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="password"]'))
        )
        pwd_field.send_keys(password)
        driver.sleep(1)
        
        # Handle Turnstile
        print("🤖 Waiting for Turnstile...", file=sys.stderr)
        driver.sleep(3)
        
        try:
            # Check if Turnstile iframe exists
            turnstile_iframe = driver.find_elements("css selector", 'iframe[src*="challenges.cloudflare.com"]')
            if turnstile_iframe:
                print("  ✅ Turnstile detected - attempting click...", file=sys.stderr)
                driver.uc_gui_click_captcha(retry=True)
                print("  ✅ Turnstile clicked!", file=sys.stderr)
                driver.sleep(5)
            else:
                print("  ℹ️  No Turnstile found (may have auto-passed)", file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️  Turnstile handling: {e}", file=sys.stderr)
        
        # Check button and click submit using uc_click
        print("🖱️  Clicking 'Create your account' (UC stealth)...", file=sys.stderr)
        try:
            # uc_click with selector string
            driver.uc_click('button:contains("Create your account")', by="css selector", reconnect_time=3)
            print("  ✅ Submitted!", file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️  Submit: {e}", file=sys.stderr)
        
        driver.sleep(8)
        
        # Check result
        current_url = driver.current_url
        page_source = driver.page_source
        
        print(f"\n📍 Final URL: {current_url}", file=sys.stderr)
        
        if "/dashboard" in current_url or "/projects" in current_url:
            print(f"\n✅ ✅ ✅ SUCCESS! Account created!", file=sys.stderr)
            print(f"📧 Email: {email}", file=sys.stderr)
            print(f"🔐 Password: {password}", file=sys.stderr)
        elif "Verification failed" in page_source or "Troubleshoot" in page_source:
            print(f"\n❌ Turnstile verification failed", file=sys.stderr)
            print(f"   Cloudflare rejected the browser/IP", file=sys.stderr)
            print(f"   Try: Different network or wait 30-60min", file=sys.stderr)
        else:
            print(f"\n⚠️  Unknown result - check manually", file=sys.stderr)
        
        # Keep open
        print("\nPress Enter to close browser...", file=sys.stderr)
        input()
        
    finally:
        driver.quit()
        print("✅ Browser closed", file=sys.stderr)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted", file=sys.stderr)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()

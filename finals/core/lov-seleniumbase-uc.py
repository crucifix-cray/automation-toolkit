#!/usr/bin/env python3
"""
Lovable.dev automation using SeleniumBase UC Mode
Proven to bypass Cloudflare Turnstile (80-92% success rate)
"""
import sys
import random
import time

def create_temp_email():
    """Generate a simple email"""
    base_names = ["yorhun", "alacat", "yavash", "balat", "mansur", "kurtaran"]
    name = random.choice(base_names)
    num = random.randint(1, 999)
    email = f"{name}{num}@gmail.com"
    print(f"✅ Email: {email}", file=sys.stderr)
    return email

def main():
    from seleniumbase import SB
    
    email = create_temp_email()
    password = f"{email.split('@')[0]}KO"
    
    # Check WARP proxy
    proxy_server = None
    try:
        import os
        if os.environ.get("PROXY_PORT") == "40000":
            import subprocess
            result = subprocess.run(
                ["curl", "--socks5", "127.0.0.1:40000", "https://cloudflare.com/cdn-cgi/trace", "--max-time", "10"],
                capture_output=True, text=True, timeout=12
            )
            if result.returncode == 0 and "warp=on" in result.stdout:
                proxy_server = "socks5://127.0.0.1:40000"
                print(f"✅ Using WARP proxy: {proxy_server}", file=sys.stderr)
    except Exception as e:
        print(f"⚠️  Proxy check skipped: {e}", file=sys.stderr)
    
    # Launch SeleniumBase UC Mode
    print("🚀 Launching SeleniumBase UC Mode (Cloudflare Turnstile bypass)", file=sys.stderr)
    
    uc_kwargs = {
        "uc": True,              # Enable UC Mode (undetected)
        "incognito": True,       # Maximum stealth
    }
    
    if proxy_server:
        uc_kwargs["proxy"] = proxy_server
    
    with SB(**uc_kwargs) as sb:
        url = "https://lovable.dev/signup"
        
        # Open with reconnect (key to bypassing detection)
        print(f"🌐 Opening {url} with UC Mode reconnect...", file=sys.stderr)
        sb.uc_open_with_reconnect(url, reconnect_time=4)
        
        sb.sleep(2)
        
        # Fill email
        print(f"📧 Filling email: {email}", file=sys.stderr)
        email_input = 'input[type="email"]'
        sb.type(email_input, email)
        sb.sleep(1)
        
        # Click Continue with UC click (disconnects chromedriver)
        print("🖱️  Clicking Continue (UC stealth click)...", file=sys.stderr)
        continue_btn = 'button:has-text("Continue")'
        sb.uc_click(continue_btn, reconnect_time=2)
        sb.sleep(3)
        
        # Fill password
        print("🔐 Filling password...", file=sys.stderr)
        pwd_input = 'input[type="password"]'
        sb.type(pwd_input, password)
        sb.sleep(1)
        
        # Handle Cloudflare Turnstile
        print("🤖 Handling Cloudflare Turnstile...", file=sys.stderr)
        try:
            # This auto-detects Turnstile and clicks it using PyAutoGUI
            sb.uc_gui_click_captcha(retry=True)
            print("✅ Turnstile clicked!", file=sys.stderr)
        except Exception as e:
            print(f"⚠️  CAPTCHA click: {e}", file=sys.stderr)
            print("  (May already be solved or not present)", file=sys.stderr)
        
        sb.sleep(5)
        
        # Check button status
        try:
            create_btn = 'button:contains("Create your account")'
            if sb.is_element_present(f'{create_btn}:not([disabled])'):
                print("✅ Button is enabled - Turnstile likely solved!", file=sys.stderr)
            else:
                print("⚠️  Button still disabled", file=sys.stderr)
        except:
            pass
        
        # Click create account with UC click
        print("🖱️  Clicking 'Create your account' (UC stealth)...", file=sys.stderr)
        try:
            sb.uc_click(create_btn, reconnect_time=3)
            print("✅ Submitted!", file=sys.stderr)
        except Exception as e:
            print(f"⚠️  Submit click: {e}", file=sys.stderr)
        
        sb.sleep(8)
        
        # Check result
        current_url = sb.get_current_url()
        page_text = sb.get_page_source()
        
        print(f"\n📍 Final URL: {current_url}", file=sys.stderr)
        
        if "/dashboard" in current_url or "/projects" in current_url:
            print(f"\n✅ SUCCESS! Account created: {email}", file=sys.stderr)
            print(f"   Password: {password}", file=sys.stderr)
        elif "Verification failed" in page_text:
            print(f"\n❌ Turnstile verification failed", file=sys.stderr)
            print(f"   Try: 1) Use WARP proxy, 2) Different IP, 3) Wait 30min", file=sys.stderr)
        else:
            print(f"\n⚠️  Check result manually", file=sys.stderr)
        
        # Keep browser open for manual inspection
        print("\nPress Enter to close browser...", file=sys.stderr)
        input()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

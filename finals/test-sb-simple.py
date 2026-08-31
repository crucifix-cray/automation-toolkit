#!/usr/bin/env python3
"""Simple SeleniumBase test"""
from seleniumbase import Driver
import sys

print("Testing SeleniumBase Driver with UC mode...", file=sys.stderr)

try:
    # Use Driver (simpler than SB)
    driver = Driver(uc=True, headless=False)
    print("✅ Browser launched!", file=sys.stderr)
    
    driver.uc_open_with_reconnect("https://example.com", 2)
    print(f"✅ Opened: {driver.title}", file=sys.stderr)
    
    driver.sleep(3)
    driver.quit()
    print("✅ Success!", file=sys.stderr)
    
except Exception as e:
    print(f"❌ Error: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()

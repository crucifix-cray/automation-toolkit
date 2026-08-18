#!/usr/bin/env python3
"""
Test dispose.lol inbox - monitor for Railway OTP codes
Similar to lovable inbox test
"""
import asyncio
from playwright.async_api import async_playwright
import json
import base64
import re
import time

class DisposeLolInbox:
    """Dispose.lol inbox monitor"""
    
    BASE_URL = "https://dispose.lol"
    API_BASE = "https://dispose.lol/_app/remote/1i1fsx0"
    
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.email = None
        self.assignment_id = None  # Store assignment ID from mailbox creation
    
    async def init_browser(self):
        """Initialize browser with session"""
        p = await async_playwright().start()
        self.browser = await p.chromium.launch(headless=True)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        
        # Load page to get session cookies
        print("🌐 Loading dispose.lol...")
        await self.page.goto(self.BASE_URL)
        await self.page.wait_for_timeout(3000)
        print("✅ Session initialized")
    
    async def _api_call(self, endpoint, payload_data=None):
        """Make API call using browser context"""
        if not self.page:
            await self.init_browser()
        
        # Build request payload
        request_body = {
            "payload": base64.b64encode(json.dumps(payload_data or [{}]).encode()).decode() if payload_data else "",
            "refreshes": []
        }
        
        url = f"{self.API_BASE}/{endpoint}"
        
        print(f"\n🔍 Making API call:")
        print(f"   URL: {url}")
        print(f"   Payload data: {payload_data}")
        print(f"   Request body: {json.dumps(request_body, indent=2)[:200]}")
        
        # Use browser to make request (has cookies/session)
        response = await self.page.evaluate(f"""
            async () => {{
                const resp = await fetch('{url}', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'x-sveltekit-pathname': '/',
                        'x-sveltekit-search': ''
                    }},
                    body: JSON.stringify({json.dumps(request_body)})
                }});
                const text = await resp.text();
                console.log('Response:', text);
                return JSON.parse(text);
            }}
        """)
        
        return response
    
    async def create_gmail(self):
        """Create temporary Gmail address"""
        print("\n📧 Creating Gmail address...")
        response = await self._api_call('getOrCreateMailbox')
        
        print(f"🔍 Create response: {json.dumps(response, indent=2)}")
        
        if response.get('type') == 'result':
            result = json.loads(response['result'])
            print(f"🔍 Parsed result: {json.dumps(result, indent=2)[:300]}")
            
            # Format: [{"address":1,"showSet":2,"error":3,"needsCaptcha":2}, "email@gmail.com", false, null]
            if len(result) >= 2:
                self.email = result[1]
                
                # Try to extract assignmentId from metadata
                if len(result) >= 1 and isinstance(result[0], dict):
                    metadata = result[0]
                    print(f"🔍 Metadata keys: {metadata.keys() if metadata else 'none'}")
                
                print(f"✅ Gmail created: {self.email}")
                return self.email
        
        raise Exception(f"Failed to create Gmail: {response}")
    
    async def get_messages_via_scraping(self):
        """Get messages by scraping the page HTML instead of API"""
        # Navigate to inbox page
        await self.page.goto(self.BASE_URL, wait_until="load")
        await self.page.wait_for_timeout(2000)
        
        # Find all message buttons: button[aria-label^="View "]
        message_buttons = await self.page.locator('button[aria-label^="View "]').all()
        
        messages = []
        for button in message_buttons:
            aria_label = await button.get_attribute('aria-label')
            if aria_label:
                # aria_label format: "View 312925 is your Railway login code"
                # Extract subject from aria-label (remove "View " prefix)
                subject = aria_label.replace('View ', '')
                
                messages.append({
                    'subject': subject,
                    'aria_label': aria_label
                })
        
        return messages
    
    async def get_messages(self):
        """Get all messages - try scraping since API fails"""
        return await self.get_messages_via_scraping()
    
    def extract_railway_otp(self, message):
        """Extract OTP code from Railway message"""
        # Get subject (from scraping it's in 'subject' or 'aria_label')
        subject = message.get('subject', '')
        aria_label = message.get('aria_label', '')
        text = message.get('text', '')
        
        # Look for Railway mentions
        content = f"{subject} {aria_label} {text}"
        if 'railway' not in content.lower():
            return None
        
        # Extract 6-digit code from subject line
        # Pattern: "312925 is your Railway login code"
        pattern = re.compile(r'\b(\d{6})\b')
        match = pattern.search(content)
        if match:
            return match.group(1)
        
        return None
    
    async def monitor_inbox(self, timeout=300):
        """Monitor inbox for Railway OTP"""
        print(f"\n👀 Monitoring inbox for Railway OTP (timeout: {timeout}s)...")
        print("📬 Send a test email to the address shown above!")
        print("=" * 60)
        
        deadline = time.time() + timeout
        check_count = 0
        
        while time.time() < deadline:
            check_count += 1
            
            messages = await self.get_messages()
            
            # Only show check count every 5 checks to reduce noise
            if check_count % 5 == 1 or len(messages) > 0:
                print(f"\n[Check #{check_count}] Found {len(messages)} message(s)")
            
            for idx, msg in enumerate(messages, 1):
                subject = msg.get('subject', 'No subject')
                aria_label = msg.get('aria_label', '')
                
                print(f"  [{idx}] Subject: {subject}")
                
                # Check if Railway message
                if 'railway' in subject.lower() or 'railway' in aria_label.lower():
                    print(f"      🚂 RAILWAY EMAIL DETECTED!")
                    print(f"      Full subject: {subject}")
                    
                    otp = self.extract_railway_otp(msg)
                    if otp:
                        print(f"      🎯 OTP CODE FOUND: {otp}")
                        print("\n" + "=" * 60)
                        print(f"✅ SUCCESS! Railway OTP is: {otp}")
                        print("=" * 60)
                        return otp
                    else:
                        print(f"      ⚠️  Railway email but no OTP found")
            
            # Wait before next check
            remaining = int(deadline - time.time())
            if remaining > 0:
                print(f"\n⏳ Waiting 5s... ({remaining}s remaining)")
                await asyncio.sleep(5)
            else:
                break
        
        print("\n❌ Timeout - no Railway OTP received")
        return None
    
    async def close(self):
        """Close browser"""
        if self.browser:
            await self.browser.close()


async def main():
    """Test the inbox monitor"""
    inbox = DisposeLolInbox()
    
    try:
        # Initialize and create email
        await inbox.init_browser()
        email = await inbox.create_gmail()
        
        print(f"\n{'='*60}")
        print(f"📬 Your test email: {email}")
        print(f"{'='*60}")
        print("\n⚠️  Now go to https://railway.app and:")
        print("   1. Click 'Log in using email'")
        print(f"   2. Enter: {email}")
        print("   3. Click 'Continue with Email'")
        print("\n   This script will detect the OTP automatically!\n")
        
        # Monitor for Railway OTP
        otp = await inbox.monitor_inbox(timeout=300)
        
        if otp:
            print(f"\n🎉 Test successful! OTP code is: {otp}")
        else:
            print(f"\n⏰ No Railway email received within timeout")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await inbox.close()


if __name__ == '__main__':
    print("🧪 Dispose.lol Inbox Monitor - Railway OTP Test")
    print("=" * 60)
    asyncio.run(main())

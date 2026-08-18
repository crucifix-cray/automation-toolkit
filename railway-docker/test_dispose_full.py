#!/usr/bin/env python3
"""Full test of dispose.lol API - create email, send test, receive"""
import asyncio
from dispose_lol_api import DisposeLolAPI
import time

async def main():
    api = DisposeLolAPI()
    
    try:
        # 1. Create Gmail
        print("=" * 60)
        print("1. Creating temporary Gmail address...")
        print("=" * 60)
        email = await api.create_gmail()
        print(f"✅ Created: {email}")
        
        # 2. Check initial messages
        print("\n" + "=" * 60)
        print("2. Checking inbox (should be empty)...")
        print("=" * 60)
        messages = await api.get_messages()
        print(f"Messages: {len(messages)}")
        if messages:
            print(json.dumps(messages, indent=2))
        
        # 3. Send test email using curl (or user can send manually)
        print("\n" + "=" * 60)
        print("3. Send a test email to:", email)
        print("=" * 60)
        print("Options:")
        print(f"  - Send from Gmail/Yahoo/etc to: {email}")
        print(f"  - Or use: https://www.gmass.co/inbox-tester")
        print(f"  - Or curl smtp service")
        print("\nWaiting 30 seconds for you to send an email...")
        
        for i in range(30, 0, -5):
            print(f"  {i}s remaining...")
            await asyncio.sleep(5)
        
        # 4. Check messages again
        print("\n" + "=" * 60)
        print("4. Checking inbox again...")
        print("=" * 60)
        messages = await api.get_messages()
        print(f"Messages: {len(messages)}")
        
        if messages:
            print("\n✅ MESSAGES RECEIVED!")
            for idx, msg in enumerate(messages):
                print(f"\n--- Message {idx + 1} ---")
                print(f"From: {msg.get('from', 'N/A')}")
                print(f"Subject: {msg.get('subject', 'N/A')}")
                print(f"Date: {msg.get('date', 'N/A')}")
                if 'text' in msg or 'html' in msg:
                    preview = msg.get('text', msg.get('html', ''))[:200]
                    print(f"Preview: {preview}...")
        else:
            print("⚠️  No messages yet")
            print("Try sending an email manually and run this script again")
        
        # 5. Keep checking for 2 minutes
        print("\n" + "=" * 60)
        print("5. Polling for messages (2 minutes)...")
        print("=" * 60)
        
        for i in range(12):  # 12 * 10s = 2 min
            messages = await api.get_messages()
            if messages:
                print(f"\n✅ Got {len(messages)} message(s)!")
                for msg in messages:
                    print(f"  - From: {msg.get('from', 'N/A')}")
                    print(f"    Subject: {msg.get('subject', 'N/A')}")
                break
            else:
                print(f"  [{i+1}/12] No messages yet... waiting 10s")
                await asyncio.sleep(10)
        
        # 6. Test creating another email
        print("\n" + "=" * 60)
        print("6. Creating another Gmail (test if API reuses or creates new)...")
        print("=" * 60)
        email2 = await api.create_gmail()
        print(f"Email 1: {email}")
        print(f"Email 2: {email2}")
        
        if email == email2:
            print("✅ API reuses same email (session-based)")
        else:
            print("✅ API creates new email each time")
        
        # 7. Get domains
        print("\n" + "=" * 60)
        print("7. Available domains...")
        print("=" * 60)
        domains = await api.get_domains()
        for d in domains:
            print(f"  - {d}")
        
        print("\n" + "=" * 60)
        print("TEST COMPLETE!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await api.close()

if __name__ == '__main__':
    asyncio.run(main())

#!/usr/bin/env python3
"""
Dispose.lol API wrapper - Gmail disposable email
"""
import asyncio
from playwright.async_api import async_playwright
import json
import base64

class DisposeLolAPI:
    """Reverse-engineered dispose.lol API"""
    
    BASE_URL = "https://dispose.lol"
    API_BASE = "https://dispose.lol/_app/remote/1i1fsx0"
    
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
    
    async def init_browser(self):
        """Initialize browser with session"""
        p = await async_playwright().start()
        self.browser = await p.chromium.launch(headless=True)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        
        # Load page to get session cookies
        await self.page.goto(self.BASE_URL)
        await self.page.wait_for_timeout(3000)
    
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
        
        # Use browser to make request (has cookies/session)
        response = await self.page.evaluate(f"""
            async () => {{
                const resp = await fetch('{url}', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({json.dumps(request_body)})
                }});
                return await resp.json();
            }}
        """)
        
        return response
    
    async def create_gmail(self):
        """
        Create temporary Gmail address
        
        Returns:
            str: Gmail address (e.g., "user123@gmail.com")
        """
        response = await self._api_call('getOrCreateMailbox')
        
        if response.get('type') == 'result':
            result = json.loads(response['result'])
            # Format: [{"address":1,"showSet":2,"error":3,"needsCaptcha":2}, "email@gmail.com", false, null]
            if len(result) >= 2:
                email = result[1]
                return email
        
        raise Exception(f"Failed to create Gmail: {response}")
    
    async def get_messages(self, assignment_id=-1):
        """
        Get messages for mailbox
        
        Args:
            assignment_id: Mailbox assignment ID (default: -1 for current)
        
        Returns:
            list: List of messages
        """
        payload = [{"assignmentId": assignment_id}]
        response = await self._api_call('getMailboxMessages', payload)
        
        if response.get('type') == 'result':
            result = json.loads(response['result'])
            # Format: [{"address":1,"mailboxKey":1,"assignmentId":1,"messages":2,...}, null, [], false, true]
            if len(result) >= 3:
                messages = result[2]
                return messages
        
        return []
    
    async def get_domains(self):
        """Get available domains"""
        response = await self._api_call('getMailDomains')
        
        if response.get('type') == 'result':
            result = json.loads(response['result'])
            # Format: [{"domains":1},[2,3],"astroai.eu.cc","cdf.dgen.lat"]
            return result[2:]  # Return domain list
        
        return []
    
    async def close(self):
        """Close browser"""
        if self.browser:
            await self.browser.close()


# Example usage
async def main():
    api = DisposeLolAPI()
    
    try:
        print("Creating temporary Gmail...")
        email = await api.create_gmail()
        print(f"✅ Got Gmail: {email}")
        
        print("\nChecking messages...")
        messages = await api.get_messages()
        print(f"Messages: {len(messages)}")
        
        print("\nAvailable domains...")
        domains = await api.get_domains()
        print(f"Domains: {domains}")
        
    finally:
        await api.close()


if __name__ == '__main__':
    asyncio.run(main())

#!/usr/bin/env python3
"""
Browser-Use Cloud - Selector Discovery for Lovable.dev

Uses Browser-Use API v4 to discover selectors on Lovable templates and chat interface.
"""

import os
import json
import time
import requests

API_KEY = "bu_Qp4WcvG5z-F7ZhFsxuY_Lb8iOJ75Hecbq6Hw_V6BeAQ"
BASE_URL = "https://api.browser-use.com/api/v4"
SESSION_DIR = "/home/alan/Documents/automation-toolkit/scripts/sessions/session-8"

# Lovable credentials from session-8
LOVABLE_EMAIL = "Fletcherjakobs@gmail.com"
LOVABLE_PASSWORD = "Fletcherjakobs@gmail.com1"


def create_run(task: str, model: str = "gpt-5.6-luna") -> dict:
    """Create a Browser-Use v4 run."""
    headers = {
        "X-Browser-Use-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "task": task,
        "model": model
    }
    
    response = requests.post(
        f"{BASE_URL}/runs",
        headers=headers,
        json=payload
    )
    response.raise_for_status()
    return response.json()


def get_run_status(run_id: str) -> dict:
    """Poll run status."""
    headers = {"X-Browser-Use-API-Key": API_KEY}
    
    response = requests.get(
        f"{BASE_URL}/runs/{run_id}/status",
        headers=headers
    )
    response.raise_for_status()
    return response.json()


def get_run(run_id: str) -> dict:
    """Fetch full run details."""
    headers = {"X-Browser-Use-API-Key": API_KEY}
    
    response = requests.get(
        f"{BASE_URL}/runs/{run_id}",
        headers=headers
    )
    response.raise_for_status()
    return response.json()


def wait_for_completion(run_id: str, timeout: int = 600) -> dict:
    """Wait for run to complete."""
    start = time.time()
    
    while time.time() - start < timeout:
        status = get_run_status(run_id)
        state = status.get("status")
        
        print(f"Status: {state}")
        
        if state in ["completed", "failed", "cancelled"]:
            return get_run(run_id)
        
        time.sleep(5)
    
    raise TimeoutError(f"Run {run_id} did not complete in {timeout}s")


def discover_templates_selectors():
    """Discover selectors on Lovable templates page."""
    
    task = f"""Go to lovable.dev and log in with:
Email: {LOVABLE_EMAIL}
Password: {LOVABLE_PASSWORD}

Then navigate to /templates page.

Find and return these selectors in JSON format:
1. template_card - The container for each template (article, div, etc)
2. template_title - Where template name is shown
3. remix_button - The button to click to use/remix a template

Return ONLY valid JSON like this:
{{
  "template_card": "article.template",
  "template_title": "h3.title",
  "remix_button": "button[data-testid='remix']"
}}
"""
    
    print("🔍 Discovering templates page selectors...")
    run = create_run(task)
    result = wait_for_completion(run["id"])
    
    return result


def discover_chat_selectors():
    """Discover selectors on Lovable chat interface."""
    
    task = f"""Go to lovable.dev, log in with:
Email: {LOVABLE_EMAIL}
Password: {LOVABLE_PASSWORD}

Pick any template and click remix to open chat interface.

Find and return these selectors in JSON format:
1. chat_input - Textarea where user types messages
2. send_button - Button to send message
3. loading_indicator - Element showing AI is working (spinner, loading text, etc)
4. pause_button - Button to pause AI work

Return ONLY valid JSON like this:
{{
  "chat_input": "textarea#chat-input",
  "send_button": "button[type='submit']",
  "loading_indicator": "div.loading-spinner",
  "pause_button": "button[aria-label='Pause']"
}}
"""
    
    print("🔍 Discovering chat interface selectors...")
    run = create_run(task)
    result = wait_for_completion(run["id"])
    
    return result


def discover_invite_link_generation():
    """Discover how to generate invite links (high credit flow)."""
    
    task = f"""Go to lovable.dev, log in with:
Email: {LOVABLE_EMAIL}
Password: {LOVABLE_PASSWORD}

Pick a template, remix it, and let AI finish building.

Then find how to generate an invite link for this project.

Return step-by-step instructions with selectors in JSON:
{{
  "steps": [
    {{"action": "click", "selector": "button.share", "description": "Click share button"}},
    {{"action": "click", "selector": "button.generate-invite", "description": "Generate invite"}},
    {{"action": "extract", "selector": "input.invite-link", "description": "Copy link from input"}}
  ]
}}
"""
    
    print("🔍 Discovering invite link generation flow...")
    run = create_run(task)
    result = wait_for_completion(run["id"])
    
    return result


def main():
    """Run all selector discoveries."""
    
    print("=" * 60)
    print("Browser-Use Selector Discovery for Lovable")
    print("=" * 60)
    
    try:
        # 1. Templates page
        templates_result = discover_templates_selectors()
        print("\n📋 Templates Page Result:")
        print(json.dumps(templates_result.get("result", "No result"), indent=2))
        
        # 2. Chat interface
        chat_result = discover_chat_selectors()
        print("\n💬 Chat Interface Result:")
        print(json.dumps(chat_result.get("result", "No result"), indent=2))
        
        # 3. Invite link generation
        invite_result = discover_invite_link_generation()
        print("\n🔗 Invite Link Generation Result:")
        print(json.dumps(invite_result.get("result", "No result"), indent=2))
        
        # Save all results
        output = {
            "templates_page": templates_result.get("result"),
            "chat_interface": chat_result.get("result"),
            "invite_generation": invite_result.get("result")
        }
        
        output_path = "/home/alan/Documents/automation-toolkit/finals/docs/SELECTORS.json"
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)
        
        print(f"\n✅ Saved to {output_path}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()

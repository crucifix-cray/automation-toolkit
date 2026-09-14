#!/usr/bin/env python3
"""
WARP Gateway - 4 Shared Proxies for 20+ Tabs

Creates 4 WARP instances, provides round-robin proxy URLs.
Saves CPU by reusing proxies instead of 1-per-tab.
"""

import subprocess
import time
import random
from pathlib import Path

WARP_SCRIPT = Path("/home/alan/Documents/automation-toolkit/finals/core/warp_multi_instance.sh")

class WARPGateway:
    """Manages 4 shared WARP proxies for high-concurrency scenarios."""
    
    def __init__(self, num_proxies=4):
        self.num_proxies = num_proxies
        self.instance_ids = []
        self.proxy_urls = []
        self.current_index = 0
        
    def start(self):
        """Start 4 WARP instances."""
        print(f"🚀 Starting {self.num_proxies} WARP gateway instances...")
        
        base_id = random.randint(10, 200)
        
        for i in range(self.num_proxies):
            instance_id = base_id + i
            port = 40000 + instance_id
            
            print(f"   [{i+1}/{self.num_proxies}] Starting instance {instance_id}...")
            
            result = subprocess.run(
                ["sudo", "bash", str(WARP_SCRIPT), str(instance_id), "start"],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                print(f"   ❌ Failed: {result.stderr}")
                continue
            
            self.instance_ids.append(instance_id)
            self.proxy_urls.append(f"socks5://127.0.0.1:{port}")
            print(f"   ✅ Instance {instance_id} ready on port {port}")
            
            time.sleep(2)
        
        print(f"\n✅ {len(self.proxy_urls)} WARP gateways ready")
        return len(self.proxy_urls) > 0
    
    def get_proxy(self):
        """Get next proxy URL (round-robin)."""
        if not self.proxy_urls:
            return None
        
        proxy = self.proxy_urls[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxy_urls)
        return proxy
    
    def get_all_proxies(self):
        """Get list of all proxy URLs."""
        return self.proxy_urls.copy()
    
    def stop(self):
        """Stop all WARP instances."""
        print(f"\n🔴 Stopping {len(self.instance_ids)} WARP gateways...")
        
        for instance_id in self.instance_ids:
            subprocess.run(
                ["sudo", "bash", str(WARP_SCRIPT), str(instance_id), "stop"],
                capture_output=True
            )
        
        print("✅ All gateways stopped")


if __name__ == "__main__":
    # Test
    gateway = WARPGateway(num_proxies=4)
    
    try:
        if gateway.start():
            print("\n📋 Proxy URLs:")
            for i, proxy in enumerate(gateway.get_all_proxies(), 1):
                print(f"   Proxy {i}: {proxy}")
            
            print("\n🔄 Round-robin test:")
            for i in range(8):
                print(f"   Tab {i+1} → {gateway.get_proxy()}")
            
            input("\nPress ENTER to stop...")
    finally:
        gateway.stop()

#!/usr/bin/env python3
"""
WARP Instance Manager
Creates isolated WARP instances with unique IPs using network namespaces

Each instance:
- Gets unique wgcf account (unique WARP IP)
- Runs in isolated network namespace
- Has own SOCKS proxy on unique port
- Fully isolated from other instances
"""

import os
import random
import subprocess
import tempfile
from pathlib import Path


class WARPInstance:
    """Manages a single isolated WARP instance."""
    
    def __init__(self):
        self.instance_id = random.randint(10, 250)  # Keep under 255 for IP addressing
        self.port = 40000 + self.instance_id
        self.script_path = Path(__file__).parent / "warp_multi_instance.sh"
        
    def create(self):
        """Create and start WARP instance."""
        print(f"🔧 Creating WARP instance {self.instance_id}...")
        
        try:
            result = subprocess.run(
                ["bash", str(self.script_path), str(self.instance_id), "start"],
                capture_output=True,
                text=True,
                timeout=120  # Increased to 120s (wgcf can be slow)
            )
            
            if result.returncode != 0:
                raise Exception(f"Failed to start instance: {result.stderr}")
            
            print(result.stdout)
            return True
            
        except subprocess.TimeoutExpired:
            raise Exception(f"Timeout starting instance (may be stuck on wgcf register)")
        except Exception as e:
            raise Exception(f"Failed to create WARP instance: {e}")
    
    def start(self):
        """Instance is started in create()."""
        return True
    
    def stop(self):
        """Stop WARP instance and cleanup."""
        print(f"\n🔴 Stopping WARP instance {self.instance_id}...")
        
        try:
            result = subprocess.run(
                ["bash", str(self.script_path), str(self.instance_id), "stop"],
                capture_output=True,
                text=True,
                timeout=30
            )
            print(result.stdout)
        except Exception as e:
            print(f"⚠️  Cleanup error: {e}")
        
        print(f"✅ WARP instance {self.instance_id} stopped")
    
    def get_proxy_url(self):
        """Get SOCKS proxy URL."""
        return f"socks5://127.0.0.1:{self.port}"
    
    def get_ip(self):
        """Get current IP of this instance."""
        try:
            result = subprocess.run(
                ["bash", str(self.script_path), str(self.instance_id), "ip"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout.strip()
        except:
            return "Unknown"


if __name__ == "__main__":
    # Test the instance manager
    print("Testing WARP Instance Manager...")
    
    instance = WARPInstance()
    
    try:
        instance.create()
        instance.start()
        
        print(f"\n✅ WARP instance running!")
        print(f"   Instance ID: {instance.instance_id}")
        print(f"   SOCKS proxy: {instance.get_proxy_url()}")
        print(f"   IP: {instance.get_ip()}")
        
        input("\nPress Enter to stop...")
        
    finally:
        instance.stop()

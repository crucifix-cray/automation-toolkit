#!/usr/bin/env python3
"""
Test client for Chimera bridge server
Tests authentication and basic message flow
"""

import asyncio
import websockets
import json
import sys

# Message types
MSG_AUTH = 1
MSG_AUTH_OK = 2
MSG_AUTH_FAIL = 3
MSG_JOB = 4
MSG_SUBMIT = 5
MSG_RESULT = 6
MSG_PING = 7
MSG_PONG = 8

async def test_bridge(url, auth_key, pool, wallet):
    """Test bridge connection"""
    print(f"Connecting to {url}...")
    
    try:
        async with websockets.connect(url, ssl=None) as ws:
            print("✓ Connected")
            
            # Send authentication
            auth_msg = {
                'type': MSG_AUTH,
                'data': {
                    'key': auth_key,
                    'pool': pool,
                    'wallet': wallet
                }
            }
            
            print(f"Sending auth: pool={pool}")
            await ws.send(json.dumps(auth_msg))
            
            # Wait for auth response
            response = await ws.recv()
            msg = json.loads(response)
            
            if msg['type'] == MSG_AUTH_OK:
                print("✓ Authentication successful")
            elif msg['type'] == MSG_AUTH_FAIL:
                reason = msg['data'].get('reason', 'unknown')
                print(f"✗ Authentication failed: {reason}")
                return False
            
            # Wait for job
            print("Waiting for job...")
            response = await ws.recv()
            msg = json.loads(response)
            
            if msg['type'] == MSG_JOB:
                job = msg['data']
                print(f"✓ Received job: {job['job_id']} (height {job['height']})")
                
                # Submit fake share
                print("Submitting share...")
                share_msg = {
                    'type': MSG_SUBMIT,
                    'data': {
                        'job_id': job['job_id'],
                        'nonce': 'test1234',
                        'result': '0000abcd'
                    }
                }
                await ws.send(json.dumps(share_msg))
                
                # Wait for result
                response = await ws.recv()
                msg = json.loads(response)
                
                if msg['type'] == MSG_RESULT:
                    accepted = msg['data'].get('accepted') == 'true'
                    if accepted:
                        print("✓ Share accepted")
                    else:
                        error = msg['data'].get('error', 'unknown')
                        print(f"✗ Share rejected: {error}")
            
            # Test ping
            print("Testing ping...")
            ping_msg = {'type': MSG_PING, 'data': {}}
            await ws.send(json.dumps(ping_msg))
            
            response = await ws.recv()
            msg = json.loads(response)
            
            if msg['type'] == MSG_PONG:
                print("✓ Ping/pong successful")
            
            print("\n✓ All tests passed!")
            return True
            
    except websockets.exceptions.WebSocketException as e:
        print(f"✗ WebSocket error: {e}")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python3 test_client.py <bridge_url>")
        print("Example: python3 test_client.py ws://localhost:8443")
        sys.exit(1)
    
    url = sys.argv[1]
    auth_key = 'test-key-12345'
    pool = 'supportxmr'
    wallet = '4AdUndXHHZ6cfufTMvppY6JwXNouMBzSkbLYfpAV5Usx3skxNgYeYTRj5UzqtReoS44qo9mtmXCqY45DJ852K5Jv2684Rge'
    
    print("=== Chimera Bridge Test Client ===")
    print(f"URL: {url}")
    print(f"Pool: {pool}")
    print("=" * 40)
    print()
    
    result = asyncio.run(test_bridge(url, auth_key, pool, wallet))
    
    sys.exit(0 if result else 1)

if __name__ == '__main__':
    main()

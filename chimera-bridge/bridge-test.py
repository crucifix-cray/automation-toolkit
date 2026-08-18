#!/usr/bin/env python3
import asyncio
import json
import socket
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Load config
with open('config-test.json', 'r') as f:
    CONFIG = json.load(f)

MSG_AUTH = 1
MSG_AUTH_OK = 2
MSG_AUTH_FAIL = 3
MSG_JOB = 4
MSG_SUBMIT = 5
MSG_RESULT = 6

class PoolConnection:
    def __init__(self, pool_url, wallet):
        self.pool_url = pool_url
        self.wallet = wallet
        self.reader = None
        self.writer = None
        
    async def connect(self):
        host, port = self.pool_url.split(':')
        port = int(port)
        
        logger.info(f"Connecting to pool: {host}:{port}")
        
        try:
            self.reader, self.writer = await asyncio.open_connection(host, port)
            
            # Stratum login
            login_msg = {
                'id': 1,
                'jsonrpc': '2.0',
                'method': 'login',
                'params': {
                    'login': self.wallet,
                    'pass': 'x',
                    'agent': 'XMRig/6.21.0'
                }
            }
            
            msg = json.dumps(login_msg) + '\n'
            self.writer.write(msg.encode())
            await self.writer.drain()
            
            logger.info("Pool login sent")
            return True
            
        except Exception as e:
            logger.error(f"Pool connection failed: {e}")
            return False
    
    async def recv(self):
        try:
            line = await self.reader.readline()
            if not line:
                return None
            return json.loads(line.decode().strip())
        except Exception as e:
            logger.error(f"Pool recv error: {e}")
            return None

async def handle_mining_test(pool_conn):
    """Simple test: connect to pool and receive job"""
    
    # Wait for pool response (login result + job)
    for _ in range(5):
        msg = await pool_conn.recv()
        if not msg:
            break
            
        logger.info(f"Pool message: {msg}")
        
        method = msg.get('method')
        if method == 'job':
            params = msg.get('params', {})
            logger.info(f"✓ Received job from pool!")
            logger.info(f"  Job ID: {params.get('job_id')}")
            logger.info(f"  Height: {params.get('height')}")
            logger.info(f"  Target: {params.get('target')}")
            return True
    
    return False

async def main():
    logger.info("=" * 60)
    logger.info("Chimera Bridge - Mining Test")
    logger.info("=" * 60)
    logger.info(f"Pool: {CONFIG['pools']['supportxmr']}")
    logger.info("")
    
    # Get wallet from command line or use config
    import sys
    wallet = sys.argv[1] if len(sys.argv) > 1 else "test-wallet"
    
    logger.info(f"Wallet: {wallet[:20]}...{wallet[-10:]}")
    logger.info("")
    
    # Connect to pool
    pool_url = CONFIG['pools']['supportxmr']
    pool_conn = PoolConnection(pool_url, wallet)
    
    if await pool_conn.connect():
        logger.info("✓ Connected to pool successfully")
        
        # Wait for job
        if await handle_mining_test(pool_conn):
            logger.info("")
            logger.info("=" * 60)
            logger.info("✓ Bridge test successful!")
            logger.info("=" * 60)
            return 0
        else:
            logger.error("Failed to receive job from pool")
            return 1
    else:
        logger.error("Failed to connect to pool")
        return 1

if __name__ == '__main__':
    asyncio.run(main())

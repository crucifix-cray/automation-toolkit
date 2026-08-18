# Chimera Bridge Server

WebSocket proxy server for mining traffic. Sits between miner clients and mining pools.

## Architecture

```
Miner Clients          Bridge Server         Mining Pools
(sandboxes)       ←→    (VPS/Cloud)      ←→  (pool.supportxmr.com)
    |                       |                       |
    |-- WSS (encrypted) ----+--- Stratum (TCP) ----+
    |                       |                       |
    +-- Disguised as        +-- Full relay          +-- Standard protocol
        normal HTTPS            with logging            (unchanged)
```

## Features

- **WebSocket Secure (WSS)**: TLS-encrypted traffic
- **Authentication**: Key-based client auth
- **Pool Proxy**: Stratum protocol relay
- **Multi-pool**: Support multiple pools with shortnames
- **Logging**: Client activity and share tracking
- **Rate Limiting**: Prevent abuse
- **Systemd Service**: Auto-restart, logging

## Installation

### Prerequisites

- Ubuntu 20.04+ or Debian 11+ VPS
- Domain name pointing to server IP
- Root access
- Open port 8443

### Quick Deploy

```bash
# On VPS as root
cd /tmp
git clone https://github.com/yourorg/chimera-bridge.git
cd chimera-bridge
chmod +x deploy.sh
./deploy.sh
```

### Manual Install

```bash
# 1. Create user
useradd -r -s /bin/false -d /opt/chimera-bridge chimera

# 2. Install dependencies
apt-get update
apt-get install -y python3 python3-pip certbot
pip3 install websockets

# 3. Deploy files
mkdir -p /opt/chimera-bridge
cp bridge.py config.json /opt/chimera-bridge/
chown -R chimera:chimera /opt/chimera-bridge

# 4. Get SSL certificate
certbot certonly --standalone -d bridge.example.com

# 5. Install service
cp systemd/chimera-bridge.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable chimera-bridge
systemctl start chimera-bridge

# 6. Firewall
ufw allow 8443/tcp
```

## Configuration

Edit `/opt/chimera-bridge/config.json`:

```json
{
  "host": "0.0.0.0",
  "port": 8443,
  "auth_keys": [
    "your-secret-key-here"
  ],
  "pools": {
    "supportxmr": "pool.supportxmr.com:3333",
    "xmrpool": "xmrpool.eu:3333"
  },
  "ssl": {
    "enabled": true,
    "cert": "/etc/letsencrypt/live/bridge.example.com/fullchain.pem",
    "key": "/etc/letsencrypt/live/bridge.example.com/privkey.pem"
  }
}
```

### Auth Keys

Generate secure auth keys:

```bash
# Random 32-char key
openssl rand -hex 16
# Output: a1b2c3d4e5f6789012345678abcdef01
```

Add to `auth_keys` array in config.

### Pool Configuration

Add pools with shortnames:

```json
"pools": {
  "supportxmr": "pool.supportxmr.com:3333",
  "xmrpool": "xmrpool.eu:3333",
  "minexmr": "pool.minexmr.com:4444",
  "hashvault": "pool.hashvault.pro:3333"
}
```

Clients reference by shortname: `"pool": "supportxmr"`

## Client Configuration

Miner clients connect with:

```json
{
  "bridge": "wss://bridge.example.com:8443",
  "key": "your-secret-key-here",
  "pool": "supportxmr",
  "wallet": "4AdUndXHHZ6cfufTMvpp..."
}
```

Or via environment variables:

```bash
export MINER_BRIDGE_URL="wss://bridge.example.com:8443"
export MINER_AUTH_KEY="your-secret-key-here"
export MINER_POOL="supportxmr"
export MINER_WALLET="4AdUndXHHZ..."
```

## Protocol

### Client → Bridge

**Authentication**:
```json
{
  "type": 1,
  "data": {
    "key": "auth-key",
    "pool": "supportxmr",
    "wallet": "4AdUndXHHZ..."
  }
}
```

**Share Submission**:
```json
{
  "type": 5,
  "data": {
    "job_id": "job123",
    "nonce": "ab12cd34",
    "result": "0000a1b2..."
  }
}
```

### Bridge → Client

**Authentication Success**:
```json
{
  "type": 2,
  "data": {}
}
```

**New Job**:
```json
{
  "type": 4,
  "data": {
    "job_id": "job123",
    "blob": "0606...",
    "target": "b88d0600",
    "height": "2950000",
    "seed_hash": "abc123..."
  }
}
```

**Share Result**:
```json
{
  "type": 6,
  "data": {
    "accepted": "true",
    "error": ""
  }
}
```

## Management

### Service Control

```bash
# Status
systemctl status chimera-bridge

# Start
systemctl start chimera-bridge

# Stop
systemctl stop chimera-bridge

# Restart
systemctl restart chimera-bridge

# Logs
journalctl -u chimera-bridge -f
```

### Monitoring

Check connections:
```bash
# Active WebSocket connections
ss -tnp | grep :8443

# Connection count
ss -tn | grep :8443 | wc -l
```

Check logs:
```bash
# Real-time logs
journalctl -u chimera-bridge -f

# Last 100 lines
journalctl -u chimera-bridge -n 100

# Today's logs
journalctl -u chimera-bridge --since today
```

### Statistics

Bridge logs show:
- New connections
- Authentication attempts (success/fail)
- Jobs relayed
- Shares submitted
- Share results (accepted/rejected)

Example log:
```
[2026-08-08 16:35:12] INFO: New connection from 203.0.113.42:51234
[2026-08-08 16:35:13] INFO: Auth attempt from 203.0.113.42:51234: pool=supportxmr
[2026-08-08 16:35:13] INFO: Client authenticated: 203.0.113.42:51234 → supportxmr
[2026-08-08 16:35:15] INFO: Job sent to 203.0.113.42:51234: job456
[2026-08-08 16:35:45] INFO: Share from 203.0.113.42:51234: job=job456
[2026-08-08 16:35:45] INFO: Share accepted from 203.0.113.42:51234
```

## Security

### SSL/TLS

- Uses Let's Encrypt certificates
- Auto-renewal via certbot
- TLS 1.2+ only
- Strong cipher suites

### Authentication

- Key-based auth prevents unauthorized access
- Keys should be 32+ characters
- Rotate keys periodically
- One key per deployment environment

### Firewall

Only port 8443 needs to be open:

```bash
# UFW (Ubuntu)
ufw allow 8443/tcp
ufw deny 3333/tcp  # Block direct pool access

# iptables
iptables -A INPUT -p tcp --dport 8443 -j ACCEPT
iptables -A INPUT -p tcp --dport 3333 -j DROP
```

### Rate Limiting

Built-in limits:
- Max clients: 1000
- Max shares/minute per client: 100

Prevents:
- DDoS attacks
- Abuse
- Excessive pool traffic

## Troubleshooting

### SSL Certificate Issues

```bash
# Check certificate
certbot certificates

# Renew certificate
certbot renew --force-renewal

# Fix permissions
setfacl -R -m u:chimera:rX /etc/letsencrypt/live/
setfacl -R -m u:chimera:rX /etc/letsencrypt/archive/
```

### Connection Refused

Check firewall:
```bash
ufw status
ss -tlnp | grep 8443
```

Check service:
```bash
systemctl status chimera-bridge
journalctl -u chimera-bridge -n 50
```

### Pool Connection Failed

Test pool connectivity:
```bash
# From bridge server
telnet pool.supportxmr.com 3333
```

Check DNS:
```bash
nslookup pool.supportxmr.com
```

### High CPU/Memory

Check client count:
```bash
ss -tn | grep :8443 | wc -l
```

Check for spam:
```bash
journalctl -u chimera-bridge | grep "Share from" | tail -100
```

Adjust limits in config.json if needed.

## Deployment Checklist

- [ ] VPS provisioned (2GB+ RAM, 1+ CPU)
- [ ] Domain name configured (A record → VPS IP)
- [ ] Firewall configured (port 8443 open)
- [ ] SSL certificate obtained (certbot)
- [ ] Auth keys generated (32+ chars)
- [ ] Pool shortnames configured
- [ ] Service installed and running
- [ ] Logs monitoring (journalctl)
- [ ] Client test connection successful

## Production Considerations

### High Availability

- Deploy multiple bridge servers
- Use DNS load balancing
- Clients fallback to direct mode if all bridges down

### Scaling

- Single server: 1000+ clients
- Add servers as needed
- Use nginx reverse proxy for >10K clients

### Monitoring

- Monitor service uptime (systemctl)
- Track connection count (ss/netstat)
- Alert on high CPU/memory
- Track share acceptance rate

### Backup

- Config file: `/opt/chimera-bridge/config.json`
- SSL certs: `/etc/letsencrypt/`
- Service file: `/etc/systemd/system/chimera-bridge.service`

## Cost Estimates

**VPS Hosting** (per month):
- Basic: $5-10 (1GB RAM, 1 CPU) - 100-500 clients
- Standard: $10-20 (2GB RAM, 2 CPU) - 500-2000 clients
- Premium: $20-40 (4GB RAM, 4 CPU) - 2000-5000 clients

**Domain Name**: $10-15/year

**SSL Certificate**: Free (Let's Encrypt)

**Total for MVP**: ~$5-10/month + domain

## Alternative Deployment

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt bridge.py config.json ./
RUN pip install -r requirements.txt
EXPOSE 8443
CMD ["python3", "bridge.py"]
```

```bash
docker build -t chimera-bridge .
docker run -d -p 8443:8443 \
  -v /etc/letsencrypt:/etc/letsencrypt:ro \
  --name chimera-bridge \
  chimera-bridge
```

### Cloud Platforms

- **AWS**: Lambda + API Gateway (WebSocket)
- **Google Cloud**: Cloud Run
- **Heroku**: Dyno with SSL
- **DigitalOcean**: App Platform

## Files

- `bridge.py` - Main server implementation
- `config.json` - Configuration
- `requirements.txt` - Python dependencies
- `deploy.sh` - Automated deployment script
- `systemd/chimera-bridge.service` - Systemd service file
- `README.md` - This documentation

## License

MIT License - See LICENSE file

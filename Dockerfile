FROM golang:1.21-alpine AS bridge-builder

WORKDIR /app
COPY cmd/bridge/main.go .
RUN go mod init chimera-bridge && go mod tidy && CGO_ENABLED=0 GOOS=linux go build -o wss-bridge .

FROM alpine:3.19

RUN apk add --no-cache \
    tor \
    tini \
    ca-certificates \
    curl

# Tor config
RUN mkdir -p /etc/tor /var/lib/tor /var/log/tor && \
    echo "SocksPort 127.0.0.1:9050" > /etc/tor/torrc && \
    echo "DataDirectory /var/lib/tor" >> /etc/tor/torrc && \
    echo "Log notice stdout" >> /etc/tor/torrc && \
    echo "Log notice file /var/log/tor/tor.log" >> /etc/tor/torrc && \
    echo "MaxCircuitDirtiness 600" >> /etc/tor/torrc && \
    echo "CircuitBuildTimeout 60" >> /etc/tor/torrc && \
    echo "LearnCircuitBuildTimeout 1" >> /etc/tor/torrc

# Bridge binary
COPY --from=bridge-builder /app/wss-bridge /usr/local/bin/wss-bridge

# Config
COPY config.json /etc/bridge/config.json
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8081/health || exit 1

ENTRYPOINT ["/sbin/tini", "--", "/entrypoint.sh"]
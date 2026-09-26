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

# Tor config comes from ./torrc (single clean instance)
COPY torrc /etc/tor/torrc
RUN mkdir -p /tmp/tordata /var/log/tor && chmod 700 /tmp/tordata

# Bridge binary

COPY --from=bridge-builder /app/wss-bridge /usr/local/bin/wss-bridge

# Config
COPY config.json /etc/bridge/config.json
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8081/health || exit 1

ENTRYPOINT ["/sbin/tini", "--", "/entrypoint.sh"]
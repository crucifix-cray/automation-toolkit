FROM ubuntu:24.04

# Long-lived "VPS" worker: sshd + git + python. Jobs arrive over `railway ssh`,
# so the image stays tiny -> fast builds across hundreds of services.
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-server git curl ca-certificates jq procps less \
      python3 python3-pip python3-venv \
      nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/run/sshd /root/.ssh \
    && printf 'PermitRootLogin prohibit-password\nPasswordAuthentication no\nPubkeyAuthentication yes\n' >> /etc/ssh/sshd_config

# The farm scripts shell out to the OnK CLI (npm package @onkernel/cli).
RUN npm install -g @onkernel/cli && kernel --version

# NOTE: no swapfile baked in — Railway's builder refuses mkswap
# ("/swapfile is mounted"). The platform already provides swap at runtime
# (/dev/vdd seen live); entrypoint enables it when present, degrades if not.

# Playwright CLIENT only — no browser. The browser is OnK's, reached over CDP.
# This is what keeps the image small and the worker inside a 1GB cell.
RUN pip3 install --no-cache-dir --break-system-packages \
      playwright 2>/dev/null || pip3 install --no-cache-dir playwright

WORKDIR /app
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 22
ENTRYPOINT ["/app/entrypoint.sh"]

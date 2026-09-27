FROM ubuntu:24.04

# Long-lived "VPS" worker: sshd + git + python. Jobs arrive over `railway ssh`,
# so the image stays tiny -> fast builds across hundreds of services.
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-server git curl ca-certificates jq procps less \
      python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/run/sshd /root/.ssh \
    && printf 'PermitRootLogin prohibit-password\nPasswordAuthentication no\nPubkeyAuthentication yes\n' >> /etc/ssh/sshd_config

# 1GB cells: swap keeps pip/playwright installs from OOMing the box.
RUN fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null \
    && echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Playwright CLIENT only — no browser. The browser is OnK's, reached over CDP.
# This is what keeps the image small and the worker inside a 1GB cell.
RUN pip3 install --no-cache-dir --break-system-packages \
      playwright 2>/dev/null || pip3 install --no-cache-dir playwright

WORKDIR /app
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 22
ENTRYPOINT ["/app/entrypoint.sh"]

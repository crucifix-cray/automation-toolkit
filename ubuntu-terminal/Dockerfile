FROM ubuntu:24.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Install base system and ttyd for web terminal
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    git \
    ca-certificates \
    python3.11 \
    python3-pip \
    wireguard-tools \
    iproute2 \
    sudo \
    jq \
    unzip \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Install wgcf for Cloudflare WARP
RUN wget -q https://github.com/ViRb3/wgcf/releases/download/v2.2.22/wgcf_2.2.22_linux_amd64 -O /usr/local/bin/wgcf && \
    chmod +x /usr/local/bin/wgcf

# Install rclone
RUN curl https://rclone.org/install.sh | bash

# Install Railway CLI
RUN curl -fsSL https://railway.com/install.sh | bash

# Install Python packages
RUN pip3 install --no-cache-dir --break-system-packages \
    patchright \
    requests \
    playwright-captcha

# Install Playwright Chromium
RUN python3 -m patchright install chromium
RUN python3 -m patchright install-deps

# Create persistent directories
RUN mkdir -p /data/railways /data/scripts /data/.config

# Set working directory
WORKDIR /data

# Copy startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Expose port for Railway
ENV PORT=8080

CMD ["/start.sh"]

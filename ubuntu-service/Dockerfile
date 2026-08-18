FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Install SSH server and basic tools
RUN apt-get update && apt-get install -y \
    openssh-server \
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
    && rm -rf /var/lib/apt/lists/*

# Setup SSH
RUN mkdir /var/run/sshd && \
    echo 'root:railway123' | chpasswd && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

# Install wgcf
RUN wget -q https://github.com/ViRb3/wgcf/releases/download/v2.2.22/wgcf_2.2.22_linux_amd64 -O /usr/local/bin/wgcf && \
    chmod +x /usr/local/bin/wgcf

# Install rclone
RUN curl https://rclone.org/install.sh | bash

# Install Railway CLI
RUN curl -fsSL https://railway.com/install.sh | bash
ENV PATH="/root/.railway/bin:$PATH"

# Install Python packages
RUN pip3 install --no-cache-dir --break-system-packages \
    patchright \
    requests \
    playwright-captcha

# Install Playwright dependencies
RUN apt-get update && apt-get install -y \
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

# Install Playwright Chromium
RUN python3 -m patchright install chromium
RUN python3 -m patchright install-deps

# Create directories
RUN mkdir -p /data/railways /data/scripts

WORKDIR /data

# Start SSH
EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]

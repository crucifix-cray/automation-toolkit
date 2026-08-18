FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Install additional dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    jq \
    wireguard-tools \
    iproute2 \
    sudo \
    ca-certificates \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install wgcf for WARP
RUN wget -O /usr/local/bin/wgcf https://github.com/ViRb3/wgcf/releases/download/v2.2.22/wgcf_2.2.22_linux_amd64 && \
    chmod +x /usr/local/bin/wgcf

# Install rclone
RUN curl https://rclone.org/install.sh | bash

# Install Railway CLI
RUN curl -fsSL https://railway.app/install.sh | sh && \
    mv ~/.railway/bin/railway /usr/local/bin/railway

# Install Python packages
RUN pip3 install --no-cache-dir \
    patchright \
    requests \
    playwright-captcha

# Browsers already included in base image, no need to install

# Create app directory
WORKDIR /app

# Copy script
COPY railway-mailtm-full.py /app/
COPY rclone.conf /root/.config/rclone/rclone.conf

# Make script executable
RUN chmod +x /app/railway-mailtm-full.py

# Create wgcf config directory
RUN mkdir -p /root

# Script will handle wgcf registration on first run
CMD ["python3", "/app/railway-mailtm-full.py", "--warp", "--continuous", "--deploy-recursive"]

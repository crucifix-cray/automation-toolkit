FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
ENV DISPLAY=:99

# Install Xvfb and required packages
RUN apt-get update && apt-get install -y \
    xvfb \
    x11-utils \
    xauth \
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
RUN wget -q https://github.com/ViRb3/wgcf/releases/download/v2.2.22/wgcf_2.2.22_linux_amd64 -O /usr/local/bin/wgcf && \
    chmod +x /usr/local/bin/wgcf

# Install rclone
RUN curl https://rclone.org/install.sh | bash

# Install Railway CLI
RUN curl -fsSL https://railway.com/install.sh | bash
ENV PATH="/root/.railway/bin:$PATH"

# Install Python packages
RUN pip3 install --no-cache-dir \
    patchright \
    requests \
    playwright-captcha

# Chrome already installed in base image

# Create app directory
RUN mkdir -p /app

WORKDIR /app

# Copy scripts
COPY railway-disposelol-full.py /app/
COPY xvfb-start.sh /app/
RUN chmod +x /app/xvfb-start.sh

# Start Xvfb and run script
CMD ["/app/xvfb-start.sh"]


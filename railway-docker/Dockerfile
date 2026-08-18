FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
ENV DISPLAY=:99

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
    xvfb \
    x11vnc \
    && rm -rf /var/lib/apt/lists/*

# Install rclone
RUN curl https://rclone.org/install.sh | bash

# Install Railway CLI
RUN curl -fsSL https://railway.app/install.sh | sh && \
    mv ~/.railway/bin/railway /usr/local/bin/railway

# Install Python packages
RUN pip3 install --no-cache-dir \
    patchright \
    requests \
    playwright-captcha \
    playwright-stealth

# Patchright will use Playwright's pre-installed Chromium from base image

# Create directories
WORKDIR /root/automation-toolkit/railway-docker
RUN mkdir -p /root/Documents/railways

# Copy all files
COPY railway-mailtm-full.py /root/automation-toolkit/railway-docker/
COPY setup-warp-railway.sh /root/automation-toolkit/railway-docker/
RUN chmod +x /root/automation-toolkit/railway-docker/*.sh

# Auto-run setup + viral script on container start
CMD ["sh", "-c", "Xvfb :99 -screen 0 1920x1080x24 > /dev/null 2>&1 & x11vnc -display :99 -forever -nopw -bg > /dev/null 2>&1 & sleep 2 && bash /root/automation-toolkit/railway-docker/setup-warp-railway.sh && cd /root/automation-toolkit/railway-docker && python3 railway-mailtm-full.py --warp --continuous --deploy-recursive"]

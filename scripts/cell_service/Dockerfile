FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y curl unzip xvfb python3-pip procps && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"
RUN uv python install 3.14 && uv venv --python 3.14 /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN uv pip install --python /opt/venv/bin/python patchright playwright camoufox playwright-stealth playwright-captcha
RUN /opt/venv/bin/python -m patchright install chromium --with-deps
RUN /opt/venv/bin/python -m camoufox fetch || true
WORKDIR /app
COPY start.sh /app/start.sh
CMD ["bash", "/app/start.sh"]

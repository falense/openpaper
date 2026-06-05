# OpenPaper Docker image
#
# Single image for interactive (claude CLI) and automated
# (claude-agent-sdk) use cases. Includes Playwright/Chromium
# for news source fetching.

FROM python:3.12-slim

# --- System dependencies ---
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      git \
      # Playwright/Chromium browser dependencies
      libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
      libatspi2.0-0 libdbus-1-3 libdrm2 libxcomposite1 \
      libxdamage1 libxfixes3 libxrandr2 libgbm1 libxcb1 \
      libxkbcommon0 libx11-6 libx11-xcb1 libxext6 libasound2 \
      libexpat1 libcups2 libpango-1.0-0 libcairo2 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Install Node.js 22 (for Claude Code npm install) ---
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Install Claude Code CLI ---
RUN npm install -g @anthropic-ai/claude-code

# --- User setup (match host UID/GID/home so bind mounts work) ---
ARG HOST_UID=1000
ARG HOST_GID=1000
ARG HOST_USER=sondre
ARG HOST_HOME=/home/sondre

RUN groupadd -g $HOST_GID $HOST_USER \
    && useradd -u $HOST_UID -g $HOST_GID -d $HOST_HOME -s /bin/bash -m $HOST_USER

# --- Install UV ---
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# --- Pre-warm UV cache with project + test dependencies ---
ENV UV_CACHE_DIR=/opt/uv-cache
RUN uv run \
    --with "jinja2>=3.1" \
    --with "httpx>=0.27" \
    --with "feedparser>=6.0" \
    --with "playwright>=1.40" \
    --with "pyyaml>=6.0" \
    --with "beautifulsoup4>=4.12" \
    --with "pytest>=8.0" \
    --with "pytest-asyncio>=0.23" \
    --with "claude-agent-sdk==0.1.37" \
    python -c "pass" \
    && chown -R $HOST_UID:$HOST_GID /opt/uv-cache

# --- Install Playwright Chromium ---
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
RUN uv run --with playwright playwright install chromium \
    && chown -R $HOST_UID:$HOST_GID /opt/playwright-browsers

USER $HOST_USER
WORKDIR $HOST_HOME/Repositories/OpenPaper

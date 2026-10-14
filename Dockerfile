# Adapted from Assignment 1 §4.3 — multi-stage python:3.13-slim image with Node
# so the filesystem, Tavily, and weather MCP servers can be launched through npx.
# Packages go to /usr/local instead of /root/.local so the non-root user can import them.

FROM python:3.13-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
    && npm install -g @modelcontextprotocol/server-filesystem tavily-mcp weather-open-meteo-mcp@0.1.2 \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /install /usr/local
COPY . .
RUN useradd -m appuser \
    && mkdir -p /app/notes /app/data /app/.npm \
    && chown -R appuser:appuser /app
ENV PATH=/usr/local/bin:$PATH \
    HOME=/home/appuser \
    NPM_CONFIG_CACHE=/app/.npm \
    NPM_CONFIG_LOGLEVEL=silent \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    NOTES_DIR=/app/notes \
    SQLITE_PATH=/app/data/research.db \
    MCP_SERVERS_CONFIG=/app/mcp_config.json
USER appuser
EXPOSE 8080
CMD ["python", "main.py"]

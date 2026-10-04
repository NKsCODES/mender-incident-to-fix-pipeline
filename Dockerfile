FROM node:22-slim AS web
WORKDIR /web
COPY dashboard/package*.json ./
RUN npm ci
COPY dashboard .
RUN npm run build

FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates && rm -rf /var/lib/apt/lists/*
# The Cursor CLI is only needed for MENDER_RUNNER=cursor.
ARG INSTALL_CURSOR_CLI=0
RUN if [ "$INSTALL_CURSOR_CLI" = "1" ]; then curl https://cursor.com/install -fsS | bash; fi
ENV PATH="/root/.local/bin:${PATH}"
WORKDIR /app
COPY backend backend
RUN pip install --no-cache-dir -e ./backend pytest
COPY mender.yaml .
COPY fixtures fixtures
COPY --from=web /web/dist dashboard/dist
ENV MENDER_DB_PATH=/data/mender.db
VOLUME /data
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=3s CMD curl -fsS http://127.0.0.1:8787/healthz || exit 1
CMD ["python", "-m", "mender", "serve", "--host", "0.0.0.0", "--port", "8787"]

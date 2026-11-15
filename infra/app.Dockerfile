# Azure image: nginx and the backend in one container. Azure Container Apps "express" environments (ours, see
# docs/deploy.md) allow one container per app and no internal-only ingress, so nginx reaches the backend on localhost
# and only nginx is exposed. Local runs keep the two images of compose.yaml.
# Build from the repo root: docker build -f infra/app.Dockerfile .

FROM node:24-bookworm-slim AS web
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.13.8 AS uv

FROM python:3.13-slim-bookworm AS venv
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM python:3.13-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx \
    && rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled /etc/nginx/conf.d/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /home/app --create-home app \
    && mkdir -p /data/cache \
    && chown app:app /data/cache
COPY --from=venv /opt/venv /opt/venv
COPY --from=web /src/dist /usr/share/nginx/html
COPY infra/app-nginx.conf /etc/nginx/nginx.conf
COPY frontend/nginx/default.conf.template /tmp/default.conf.template
RUN sed 's#${BACKEND_URL}#http://127.0.0.1:8000#g' /tmp/default.conf.template > /etc/nginx/conf.d/default.conf \
    && rm /tmp/default.conf.template \
    && mkdir -p /tmp/nginx && nginx -t && rm -rf /tmp/nginx
COPY --chmod=755 infra/app-start.sh /usr/local/bin/app-start
WORKDIR /srv
COPY backend/app ./app
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SPHEREX_CACHE_DIR=/data/cache
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=4)"]
CMD ["app-start"]

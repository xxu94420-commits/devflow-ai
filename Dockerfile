FROM node:24-alpine AS web
WORKDIR /web
RUN corepack enable && corepack prepare pnpm@11.19.0 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
# Same origin: no browser requests to localhost and no cross-origin API setup.
ENV VITE_API_URL=""
RUN pnpm build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    READ_ONLY=true DATABASE_URL=sqlite:////data/public-demo.db \
    STATIC_DIR=/app/static PORT=8000
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd -u 10001 -m devflow \
    && mkdir /data && chown devflow /data
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
COPY --from=web /web/dist ./static
USER devflow
EXPOSE 8000
CMD ["python", "-m", "app.public_server"]

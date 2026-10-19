# Virtual Energy Lab — single container: FastAPI (API + solver) serving the built React app.
# Build:  docker build -t virtual-energy-lab .
# Run:    docker run -p 8080:8080 -v vel-data:/data virtual-energy-lab
# Cloud Run sets $PORT; the database URL comes from VEL_DATABASE_URL (see docs/deploy-cloud-run.md).

# ---- stage 1: frontend build ----
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

# ---- stage 2: runtime ----
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    VEL_STATIC_DIR=/app/static VEL_DATA_DIR=/data PORT=8080
WORKDIR /app
COPY backend/pyproject.toml ./backend/
COPY backend/vel ./backend/vel
RUN pip install --no-cache-dir ./backend psycopg[binary]
COPY --from=web /web/dist ./static
RUN useradd --create-home --uid 10001 vel && mkdir -p /data && chown vel /data
USER vel
EXPOSE 8080
CMD ["sh", "-c", "uvicorn --factory vel.main:create_app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]

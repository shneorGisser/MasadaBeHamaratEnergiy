# Hugging Face Space (Docker SDK) for the Virtual Energy Lab.
# The Space holds only this file and README.md; the code is cloned from GitHub at build time,
# so "Factory rebuild" in the Space settings deploys the latest main. Guide (Hebrew):
# docs/deploy-huggingface.md in the GitHub repository.

# ---- stage 1: source + frontend build ----
FROM node:22-bookworm-slim AS src
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ARG REPO=https://github.com/shneorGisser/MasadaBeHamaratEnergiy.git
ARG REF=main
# changes whenever main moves, so the clone below is never served from a stale build cache
ADD https://api.github.com/repos/shneorGisser/MasadaBeHamaratEnergiy/commits/main /tmp/head.json
RUN git clone --depth 1 --branch "$REF" "$REPO" /src
WORKDIR /src/frontend
RUN npm ci --ignore-scripts && npm run build

# ---- stage 2: runtime ----
FROM python:3.13-slim
# VEL_WORKSPACES=cookie: every visitor gets a private workspace (no accounts).
# Set VEL_ADMIN_TOKEN as a Space *secret* to read the feedback on /feedback.
# /data is lost on restart unless a storage bucket is attached to the Space (mounted at /data).
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    VEL_STATIC_DIR=/app/static VEL_DATA_DIR=/data VEL_WORKSPACES=cookie PORT=7860
WORKDIR /app
COPY --from=src /src/backend /app/backend
RUN pip install --no-cache-dir ./backend
COPY --from=src /src/frontend/dist ./static
RUN useradd -m -u 1000 user && mkdir -p /data && chmod 777 /data
USER user
EXPOSE 7860
CMD ["sh", "-c", "uvicorn --factory vel.main:create_app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]

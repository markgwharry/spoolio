# ---------------------------------------------------------------------------
# Stage 1: build the React frontend
# ---------------------------------------------------------------------------
FROM node:24-slim AS frontend

WORKDIR /frontend

# Install dependencies first so this layer is cached across source changes.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

# Build the production bundle.
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Runtime libraries for Pillow (JPEG/PNG/zlib/freetype) plus curl for healthchecks.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        zlib1g \
        libfreetype6 \
        libpng16-16 \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_ENV=production \
    REGISTRATION_MODE=first-user \
    GUNICORN_WORKERS=2 \
    GUNICORN_THREADS=4

WORKDIR /app

# Install Python dependencies first for layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source.
COPY . .

# Drop source-only hardware and documentation from the runtime image.
RUN rm -rf hardware docs spoolWeights.pdf

# Bring in the freshly built frontend. The Flask app serves ./static.
RUN rm -rf static
COPY --from=frontend /frontend/build ./static

# Persisted state lives under these directories; mount volumes here.
RUN mkdir -p instance shared/profile_images

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Run as an unprivileged user.
RUN useradd --create-home --uid 1000 spoolio \
    && chown -R spoolio:spoolio /app
USER spoolio

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "wsgi:app"]

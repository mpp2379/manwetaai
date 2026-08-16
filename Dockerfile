FROM python:3.11-slim

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt /app/requirements.txt

# Install Python deps
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /app/requirements.txt

# Create a non-root user and app directories
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/static/uploads /app/static/outputs \
    && chown -R appuser:appuser /app

# Copy application code as non-root
COPY --chown=appuser:appuser . /app

ENV FLASK_APP=app.py

# Expose default app port; App Service may set $PORT
EXPOSE 5000

# Switch to non-root user
USER appuser

# Healthcheck — verifies the app responds on the root path using Python
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\", \"5000\")}/', timeout=5)" || exit 1

# Use gunicorn to run the Flask app
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} app:app --workers 1 --threads 4"]
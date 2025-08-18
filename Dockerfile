FROM python:3.13.7-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PROMETHEUS_MULTIPROC_DIR=/tmp

# Gunicorn configuration environment variables
ENV PORT=1968
ENV GUNICORN_WORKERS=4
ENV GUNICORN_LOG_LEVEL=info

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
    && rm -rf /var/lib/apt/lists/*

# Create directory for Prometheus multiprocess
RUN mkdir -p /tmp
RUN mkdir -p /data
RUN mkdir -p /target

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Expose port (will be overridden by PORT env var)
EXPOSE 1968

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://0.0.0.0:${PORT:-1968}/health || exit 1

# Run the application with gunicorn using configuration file
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app.main:app"]

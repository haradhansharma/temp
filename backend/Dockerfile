# sattabase/backend/Dockerfile
# Stage 1: Build dependencies
FROM python:3.10-slim AS builder

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PATH="/home/appuser/.local/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -ms /bin/bash appuser

WORKDIR /app
# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local
COPY . .

# Create folders and ensure appuser owns them
RUN mkdir -p /app/logs /app/staticfiles /app/media && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app/media

USER appuser

EXPOSE 8086

# Production uses Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8086", "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "base.asgi:application"]
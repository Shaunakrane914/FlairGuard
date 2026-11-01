# Multi-stage Dockerfile for FlairGuard AI Platform
# Tata Elxsi Teliport S4 Case Study 1

# Stage 1: Build Modern React/TypeScript Frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python Backend Runtime & Static Serving
FROM python:3.13-slim AS runtime

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt ./
COPY requirements-serving.lock.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements-serving.lock.txt

# Copy Python codebase, models, and NASA data
COPY FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/ /app/

# Create separate dedicated storage directory for mutable SQLite databases
RUN mkdir -p /app/storage /app/mlruns

# Copy built frontend assets into the directory expected by FastAPI static mount
COPY --from=frontend-builder /app/dist /app/frontend/dist

# Set operational environment variables (points DB to dedicated storage dir to prevent volume masking)
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    FLAIRGUARD_DB_PATH=/app/storage/flairguard_platform.db \
    FLAIRGUARD_DATA_DIR=/app/data/raw

# Expose HTTP port for API and Dashboard
EXPOSE 8000

# Container Healthcheck
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Launch production Uvicorn ASGI server
CMD ["uvicorn", "flairguard.service.app:app", "--host", "0.0.0.0", "--port", "8000"]

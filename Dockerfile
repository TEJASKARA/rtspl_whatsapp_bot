# ─────────────────────────────────────────────
# Dockerfile — Optimized for Google Cloud Run
# ─────────────────────────────────────────────
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY . .

# Cloud Run injects PORT env variable (default 8080)
ENV PORT=8080

# Start FastAPI with uvicorn
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
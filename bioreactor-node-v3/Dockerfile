FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies for native Python extensions (lgpio, numpy, etc.)
RUN apt-get update && apt-get install -y \
    build-essential \
    libgpiod-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtualenv and install Python dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Runtime stage ---
FROM python:3.11-slim

WORKDIR /app

# Install only the runtime library needed by lgpio (~1MB vs ~200MB+ for build tools)
RUN apt-get update && apt-get install -y \
    libgpiod3 \
    && rm -rf /var/lib/apt/lists/*

# Copy the pre-built virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy bioreactor_v3 source
COPY bioreactor_v3/ ./bioreactor_v3/

# Copy application source
COPY src/ ./src/

# Copy custom hardware config
COPY config_hardware.py ./

# Create necessary directories
RUN mkdir -p /app/data/experiments /app/logs

# Expose API port
EXPOSE 9000

# Health check using stdlib (no external dependency)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9000/health')"

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "9000"]

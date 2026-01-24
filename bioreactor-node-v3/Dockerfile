FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libgpiod-dev \
    git \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:9000/health').raise_for_status()"

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "9000"]

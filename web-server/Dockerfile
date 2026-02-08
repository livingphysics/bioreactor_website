# This is the Docker image for the bioreactor website.
# It is used to run the Python code on the bioreactor.
# It is based on the Python 3.9 image.
# It is used to run the Python code on the bioreactor.
# It lives on the bioreactor.
FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY templates/ ./templates/
COPY static/ ./static/

# Create uploads directory
RUN mkdir -p uploads_tmp

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/')" || exit 1

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "3000"]

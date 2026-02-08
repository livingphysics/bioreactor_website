FROM python:3.11-slim

WORKDIR /app

# Install allowed packages
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    matplotlib \
    scikit-learn \
    requests \
    scipy \
    pillow

# Create output directory
RUN mkdir -p /app/output

# Copy bioreactor client library
COPY bioreactor_client.py /app/bioreactor_client.py

# Make client importable
ENV PYTHONPATH=/app:$PYTHONPATH

# Script will be mounted at runtime
# /app/experiments/{id}/user_script.py - user's experiment script
# /app/output - output directory (read-write)

CMD ["python", "/app/user_script.py"]

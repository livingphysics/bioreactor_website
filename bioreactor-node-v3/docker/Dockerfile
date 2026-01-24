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

# Script and client will be mounted at runtime
# /app/user_script.py - user's experiment script (read-only)
# /app/bioreactor_client.py - auto-generated API client (read-only)
# /app/output - output directory (read-write)

CMD ["python", "/app/user_script.py"]

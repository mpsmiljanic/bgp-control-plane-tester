# Use a lightweight, official Python image optimized for embedded scripts
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Install system utilities needed for serial communication
RUN apt-get update && apt-get install -y --no-install-recommends \
    udev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python requirements first (utilizing Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the configuration and test files into the container
COPY config/ ./config/
COPY tests/ ./tests/

# Default entrypoint: Run the BGP FSM test suite in verbose mode
CMD ["pytest", "-s", "-v", "tests/test_bgp_fsm.py"]

# Base image with CUDA runtime and minimal dependencies
FROM nvidia/cuda:12.1.1-base-ubuntu22.04

# Install minimal Python and essential packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3-minimal python3-pip python3-distutils python3-setuptools && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    python3 -m pip install --no-cache-dir --upgrade pip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install only necessary Python packages
RUN pip install --no-cache-dir fastapi uvicorn
RUN pip install --no-cache-dir torch==2.3.0+cu121 torchvision==0.18.0+cu121 --index-url https://download.pytorch.org/whl/cu121
RUN pip install --no-cache-dir transformers
RUN pip uninstall -y torchvision
RUN pip cache purge

# Set the working directory
WORKDIR /app

# Copy application code
COPY . .

# Expose application port
EXPOSE 10002

# Command to run the FastAPI application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "10002"]

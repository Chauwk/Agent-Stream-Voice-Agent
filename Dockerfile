FROM python:3.10-slim

# Install SIP dependencies
RUN apt-get update && apt-get install -y \
    libpjproject2.x \
    libpjproject2-dev \
    portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .

# Expose SIP port
EXPOSE 5060/udp
EXPOSE 5060/tcp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import socket; s = socket.socket(); s.connect(('localhost', 5060)); s.close()" || exit 1

# Start bot
CMD ["python", "main.py"]

FROM python:3.10-slim

# Install audio and build dependencies
RUN apt-get update && apt-get install -y \
    portaudio19-dev \
    ffmpeg \
    build-essential \
    swig \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Build PJSIP and PJSUA2 Python bindings
WORKDIR /usr/src
RUN wget https://github.com/pjsip/pjproject/archive/refs/tags/2.13.tar.gz && \
    tar -xvzf 2.13.tar.gz && \
    cd pjproject-2.13 && \
    ./configure CFLAGS="-O2 -fPIC" --enable-shared && \
    make dep && make && \
    cd pjsip-apps/src/swig/python && \
    make && make install && \
    cd /usr/src && rm -rf pjproject-2.13 2.13.tar.gz

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .

# Expose API ports (5000 API, 5060 SIP)
EXPOSE 5000/tcp 5060/tcp 5060/udp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/')" || exit 1

# Start bot
CMD ["python", "main.py"]

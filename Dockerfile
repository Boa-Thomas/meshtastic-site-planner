FROM python:3.11-slim

ENV HOME="/root"
ENV TERM=xterm

# Install system dependencies first (before Python dependencies)
RUN apt-get update && apt-get install -y \
    build-essential \
    libbz2-dev \
    gdal-bin \
    libgdal-dev \
    && apt-get clean

# Set the working directory
WORKDIR /app

# Copy requirements first to leverage Docker caching
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Change to SPLAT directory and fix line endings + set permissions
WORKDIR /app/splat
RUN sed -i 's/\r//' build configure install && \
    chmod +x build && chmod +x configure && chmod +x install

# Modify build script and configure SPLAT
RUN sed -i.bak 's/-march=\$cpu/-march=native/g' build && \
    printf "8\n4\n" | ./configure && \
    ./install splat
# RUN cp ./splat /app/splat

# SPLAT utils including srtm2sdf
WORKDIR /app/splat/utils
RUN sed -i 's/\r//' build && chmod +x build
RUN ./build all && cp srtm2sdf /app && cp srtm2sdf-hd /app
RUN cp -a ./ /app/splat

WORKDIR /app

# Set executable permissions in a single layer
RUN chmod +x /app/splat/splat \
    /app/splat/srtm2sdf \
    /app/splat/citydecoder \
    /app/splat/bearing \
    /app/splat/fontdata \
    /app/splat/usgs2sdf

# Create non-root user and set ownership
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser
ENV HOME="/home/appuser"

# Expose the application port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/')"]
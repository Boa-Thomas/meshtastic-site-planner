# =============================================================================
# Stage 1: frontend-builder
# -----------------------------------------------------------------------------
# Build the Vue/Vite frontend ahead of the Python image so the runtime
# container ships with raw .js/.css *and* their pre-compressed .br/.gz
# siblings already in place under app/ui/. This decouples local-dev state
# (the host's app/ui/ may be empty or stale, and the .gitignore excludes
# raw assets from the repo) from production: the Docker build is now
# self-sufficient.
# =============================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app

# Use pnpm via corepack so the version is pinned to what the project uses.
# Lockfile is v9 (pnpm >=9). pnpm@10 reads it correctly.
RUN corepack enable && corepack prepare pnpm@10.33.2 --activate

# Install deps first — cached as long as the lockfile doesn't change.
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Copy the rest of the build inputs. We do this AFTER `pnpm install` so
# source changes don't bust the dependency cache.
COPY vite.config.ts tsconfig.json tsconfig.app.json tsconfig.node.json index.html ./
COPY src ./src
COPY public ./public

# `pnpm run build` runs `vue-tsc -b && vite build && cp -r public/* app/ui`.
# Output: /app/app/ui with index.html + assets/*.js + assets/*.css + .br + .gz.
RUN pnpm run build


# =============================================================================
# Stage 2: backend runtime (Python + SPLAT!)
# =============================================================================
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

# Copy the rest of the application files. `.dockerignore` excludes
# `app/ui/` so we don't pollute the image with the host's local (possibly
# stale) build — the next COPY brings the freshly-built artifacts in.
COPY . .

# Overlay the freshly-built frontend produced by Stage 1.
COPY --from=frontend-builder /app/app/ui /app/app/ui

# Change to SPLAT directory and fix line endings + set permissions
WORKDIR /app/splat
RUN sed -i 's/\r//' build configure install && \
    chmod +x build && chmod +x configure && chmod +x install

# Modify build script and configure SPLAT (use -O3 for max vectorization/inlining)
RUN sed -i.bak 's/-march=\$cpu/-march=native/g' build && \
    sed -i 's/-O2/-O3/g' build && \
    printf "8\n4\n" | ./configure && \
    sed -i 's/#define MAXPAGES 64/#define MAXPAGES 225/' std-parms.h && \
    echo '#define ARRAYSIZE 270225' >> std-parms.h && \
    ./install splat
# RUN cp ./splat /app/splat

# SPLAT utils including srtm2sdf
WORKDIR /app/splat/utils
RUN sed -i 's/\r//' build && chmod +x build
RUN sed -i 's/-O2/-O3/g' build && \
    ./build all && cp srtm2sdf /app && cp srtm2sdf-hd /app
RUN cp -a ./ /app/splat

# Build Signal Server (optional — non-fatal if build fails)
WORKDIR /app
RUN apt-get update && apt-get install -y cmake git && apt-get clean || true
RUN git clone --depth 1 https://github.com/Cloud-RF/Signal-Server.git /tmp/signal-server && \
    cd /tmp/signal-server && \
    mkdir build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release && \
    make -j$(nproc) && \
    cp src/signalserver /usr/local/bin/signalserverHD && \
    cp src/signalserver /usr/local/bin/signalserver && \
    cd /app && rm -rf /tmp/signal-server || echo "Signal Server build skipped (optional)"

WORKDIR /app

# Set executable permissions in a single layer
RUN chmod +x /app/splat/splat \
    /app/splat/srtm2sdf \
    /app/splat/citydecoder \
    /app/splat/bearing \
    /app/splat/fontdata \
    /app/splat/usgs2sdf

# Create non-root user and set ownership
RUN mkdir -p /app/.splat_tiles /app/app/data/rasters && \
    useradd -m appuser && \
    chown -R appuser:appuser /app
USER appuser
ENV HOME="/home/appuser"

# Expose the application port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/')"]
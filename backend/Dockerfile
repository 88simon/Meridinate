# Multi-stage Dockerfile for Gun Del Sol Backend
# Produces a minimal, security-hardened production image

# Stage 1: Builder - compile dependencies and prepare environment
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /build

# Install system dependencies needed for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first for better layer caching
COPY backend/requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies in virtual environment
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt


# Stage 2: Runtime - minimal production image
FROM python:3.11-slim

# Set metadata labels
LABEL maintainer="Gun Del Sol Team"
LABEL description="FastAPI backend for Solana token analysis"
LABEL version="2.0.0"

# Create non-root user for security
RUN groupadd -r gundelsoladm && useradd -r -g gundelsoladm gundelsoladm

# Set working directory
WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy backend application code
COPY backend/app ./app
COPY backend/*.py ./

# Create directories for persistent data
RUN mkdir -p data analysis_results axiom_exports && \
    chown -R gundelsoladm:gundelsoladm /app

# Copy default config template (real config mounted as volume)
COPY backend/config.example.json ./config.example.json

# Switch to non-root user
USER gundelsoladm

# Expose FastAPI port
EXPOSE 5003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5003/api/settings').read()" || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5003

# Run FastAPI with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5003", "--proxy-headers", "--forwarded-allow-ips", "*"]
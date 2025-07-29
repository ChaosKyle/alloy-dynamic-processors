# Multi-stage build for optimized production image
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Create non-root user for security
RUN groupadd -r aisorter && useradd -r -g aisorter aisorter

# Set working directory
WORKDIR /app

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/aisorter/.local

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/logs /app/config \
    && chown -R aisorter:aisorter /app

# Switch to non-root user
USER aisorter

# Add local Python packages to PATH
ENV PATH=/home/aisorter/.local/bin:$PATH

# Set Python path
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Default command
CMD ["python", "main.py"]
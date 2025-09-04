# Use Python 3.9 slim image for smaller size
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies (skip if network issues)
RUN apt-get update || echo "Network issue, continuing..." && \
    apt-get install -y gcc || echo "GCC install failed, continuing..." && \
    rm -rf /var/lib/apt/lists/* || true

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create directory for database and logs
RUN mkdir -p /app/data

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash botuser && \
    chown -R botuser:botuser /app

# Switch to non-root user
USER botuser


# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python", "main.py"]

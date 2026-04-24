FROM python:3.11-slim

WORKDIR /app

# Install build tools needed by some chromadb deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# I-4 FIX: Run as a non-root user — standard security practice for production
# containers. If there is any path traversal / code injection vulnerability,
# the attacker gets an unprivileged user instead of root.
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app
USER appuser

# Fix #16: Removed VOLUME declaration — anonymous volumes silently persist
# chroma_data in an untracked Docker location and break `docker-compose down -v`.
# Volume mounts are defined exclusively in docker-compose.yml.

EXPOSE 5000

# Fix #5: Use Gunicorn (production WSGI server) instead of Flask's dev server.
# workers=1 keeps Chroma's in-memory collection in a single process.
# threads=4 handles concurrent requests within that process.
CMD ["gunicorn", "--workers", "1", "--threads", "4", \
     "--bind", "0.0.0.0:5000", "--timeout", "120", "app:app"]

#!/bin/bash
# Docker entrypoint script for API container
# Automatically runs migrations in dev mode before starting uvicorn

set -e

echo "=== Docker Entrypoint: Starting API ==="

# Wait for PostgreSQL to be ready (only in dev mode)
if [ "${AUTO_MIGRATE:-0}" = "1" ] || [ "${AUTO_MIGRATE:-0}" = "true" ]; then
    echo "AUTO_MIGRATE enabled, waiting for PostgreSQL..."
    
    # Wait for PostgreSQL (max 30 seconds)
    for i in {1..30}; do
        if python -c "from app.db import engine; engine.connect()" 2>/dev/null; then
            echo "✓ PostgreSQL is ready"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "⚠ PostgreSQL not ready after 30 seconds, continuing anyway..."
        else
            echo "  Waiting for PostgreSQL... ($i/30)"
            sleep 1
        fi
    done
    
    # Run migrations
    echo "Running Alembic migrations..."
    alembic upgrade head
    echo "✓ Migrations completed"
else
    echo "AUTO_MIGRATE disabled, skipping automatic migrations"
    echo "Run manually: docker compose exec api alembic upgrade head"
fi

# Execute the main command (uvicorn)
echo "=== Starting uvicorn ==="
exec "$@"

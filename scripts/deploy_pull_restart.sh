#!/bin/bash
set -euo pipefail

echo "🚀 Starting deployment..."

# Check prerequisites
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ docker-compose.yml not found"
    exit 1
fi

if [ ! -d ".git" ]; then
    echo "❌ .git directory not found"
    exit 1
fi

# Update code
echo "📥 Fetching latest changes..."
git fetch --all --prune

echo "🔄 Switching to p3/wb-ingest-warehouses branch..."
git checkout p3/wb-ingest-warehouses

echo "⬇️ Pulling latest changes..."
git pull --ff-only

# Update and restart services
echo "🐳 Pulling latest images..."
docker compose pull || true

echo "🔨 Building and starting services..."
docker compose up -d --build

echo "📊 Checking service status..."
docker compose ps

echo "✅ Deployment completed successfully!"
echo "📝 To test warehouses ingest:"
echo "   docker compose exec api sh -lc 'python -m app.ingest_warehouses --dry-run'"

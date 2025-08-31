#!/bin/bash
# Build frontend and copy to backend for Railway deployment

echo "🔨 Building frontend..."
cd frontend
pnpm install --frozen-lockfile
pnpm build

echo "📁 Copying frontend build to backend..."
cd ..
rm -rf backend/static
cp -r frontend/.next backend/static

echo "✅ Frontend build complete and copied to backend/static"

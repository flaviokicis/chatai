# 🚀 ChatAI Development & Production Modes

## 🛠️ Development Mode (Default)

**Frontend and Backend run separately for optimal development experience.**

### Commands:
```bash
# Terminal 1: Backend API only
cd backend && make dev

# Terminal 2: Frontend with hot reload
cd frontend && pnpm dev
```

### URLs:
- **Frontend**: `http://localhost:3000/controller` (Next.js dev server)
- **Backend API**: `http://localhost:8080/api/controller/*` (Python FastAPI)

### Features:
- ✅ **Hot reload** for frontend changes
- ✅ **Fast development** iteration
- ✅ **Separate debugging** for frontend/backend
- ✅ **CORS enabled** for cross-origin requests

---

## 🐛 Debug Mode (Production-like serving locally)

**Test production-like behavior locally for debugging client-side issues.**

### Commands:
```bash
# Build frontend first
cd frontend && pnpm build

# Start backend with frontend serving enabled
cd backend && SERVE_FRONTEND=true make dev
```

### URLs:
- **Everything**: `http://localhost:8080/controller` (Python serves all)
- **API**: `http://localhost:8080/api/controller/*`

### Features:
- ✅ **Production-like** serving behavior
- ✅ **Debug client-side** issues
- ✅ **Test SPA routing** locally
- ✅ **Same as Railway** deployment

---

## 🚀 Production Mode (Railway)

**Single Python server serves both frontend and API efficiently.**

### Environment:
```bash
NODE_ENV=production  # Automatically set by Railway
```

### URLs:
- **Frontend**: `https://your-app.railway.app/controller`
- **API**: `https://your-app.railway.app/api/controller/*`

### Features:
- ✅ **Single container** deployment
- ✅ **Optimized** static file serving
- ✅ **Clean URLs** with SPA routing
- ✅ **No CORS issues** (same origin)

---

## 🎯 Quick Commands

```bash
# Normal development
make dev (backend) + pnpm dev (frontend)

# Debug production issues locally  
SERVE_FRONTEND=true make dev

# Deploy to production
git push railway main
```

## 🔧 Environment Variables

### Development:
- `ADMIN_PASSWORD=admin123`
- `SESSION_SECRET_KEY=dev-key`
- `PII_ENCRYPTION_KEY=dev-key`

### Production (Railway):
- `NODE_ENV=production` (auto-set)
- `ADMIN_PASSWORD=secure-password`
- `SESSION_SECRET_KEY=secure-key`
- `PII_ENCRYPTION_KEY=secure-key`
- `DATABASE_URL=postgresql://...` (auto-set)
- `REDIS_URL=redis://...` (auto-set)

Your development workflow is now optimized for both speed and debugging! 🎯

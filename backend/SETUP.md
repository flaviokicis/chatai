# ChatAI Backend Setup Guide

Quick setup guide for developers to get the WhatsApp automation service running locally.

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 12+
- Redis 6+ (optional, falls back to memory)
- uv (Python package manager)

### 1. Clone & Install

```bash
git clone <repository>
cd chatai/backend

# Install dependencies
uv sync

# Activate virtual environment
source .venv/bin/activate
```

### 2. Database Setup

```bash
# Start PostgreSQL (macOS with Homebrew)
brew services start postgresql

# Create database
createdb chatai

# Or using psql
psql -c "CREATE DATABASE chatai;"
```

### 3. Environment Configuration

```bash
# Copy environment template
cp env.example .env

# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Edit .env file
nano .env
```

**Required Environment Variables:**

```bash
# Database
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/chatai

# Encryption (CRITICAL - use generated key above)
PII_ENCRYPTION_KEY=your-generated-key-here

# LLM (get from Google AI Studio)
GOOGLE_API_KEY=your-google-api-key

# Optional: Redis
REDIS_URL=redis://localhost:6379/0

# Optional: Twilio (for WhatsApp)
TWILIO_AUTH_TOKEN=your-twilio-token
PUBLIC_BASE_URL=https://your-ngrok-url.ngrok.io
```

### 4. Initialize Database

```bash
# Set up database with example data (recommended for development)
make setup-db

# Or manually:
# make reset-db    # Create tables
# make seed-db     # Add example tenant + flow
```

**What the seed creates:**

- Demo tenant: "ChatAI Demo" (demo@chatai.com)
- WhatsApp channel: +5511999999999
- Example flow: Sports lighting sales qualification
- Project context: LED lighting company targeting sports facilities

### 5. Start Services

```bash
# Terminal 1: Start Redis (optional)
redis-server

# Terminal 2: Start API server
make dev

# Or manually:
# uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Verify Setup

```bash
# Test database connection
python test_db_setup.py

# Check API health
curl http://localhost:8000/health

# View API documentation
open http://localhost:8000/docs
```

## 🧪 Test the System

### Using Seeded Data

If you ran `make setup-db`, you already have everything needed:

```bash
# View the created tenant
curl http://localhost:8000/admin/tenants

# View the WhatsApp channel
curl http://localhost:8000/admin/tenants/{tenant_id}/channels

# View the example flow
curl http://localhost:8000/admin/tenants/{tenant_id}/flows
```

### Manual Setup (Alternative)

If you prefer to create data manually instead of using seed:

```bash
# Create tenant
curl -X POST http://localhost:8000/admin/tenants \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Test",
    "last_name": "User",
    "email": "test@example.com",
    "project_description": "Test fitness studio",
    "target_audience": "Test audience",
    "communication_style": "Friendly"
  }'

# Add WhatsApp channel (use tenant ID from above)
curl -X POST http://localhost:8000/admin/tenants/{tenant_id}/channels \
  -H "Content-Type: application/json" \
  -d '{
    "channel_type": "whatsapp",
    "identifier": "whatsapp:+14155238886",
    "phone_number": "+14155238886"
  }'

# Upload flow (use tenant_id and channel_id from above)
curl -X POST http://localhost:8000/admin/tenants/{tenant_id}/flows \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Example Flow",
    "flow_id": "flow.example",
    "channel_instance_id": "{channel_id}",
    "definition": {...}
  }'
```

## 🔧 Development Tools

### Database Management

```bash
# Connect to database
psql chatai

# View tables
\dt

# Check tenant data
SELECT id, owner_first_name, owner_email FROM tenants;

# View encrypted data (will show ciphertext)
SELECT owner_email FROM tenants;
```

### Testing Webhooks Locally

```bash
# Install ngrok
brew install ngrok

# Expose local server
ngrok http 8000

# Use the HTTPS URL in Twilio webhook configuration
# https://abc123.ngrok.io/webhooks/twilio/whatsapp
```

### Available Makefile Commands

```bash
# Development
make install      # Install dependencies
make dev         # Start API server with reload
make test        # Run tests
make lint        # Check code quality
make fmt         # Format code

# Database
make reset-db    # Drop and recreate all tables (⚠️ DANGEROUS)
make seed-db     # Add example tenant, channel, and flow
make setup-db    # Complete setup: reset + seed (recommended for dev)

# Flow testing
make flow        # Test flow interactively (manual mode)
make flow-llm    # Test flow with LLM assistance
```

### Manual Commands (Alternative)

```bash
# Run linter
ruff check .

# Format code
ruff format .

# Type checking
mypy .

# Run tests
pytest
```

## 📁 Project Structure

```
backend/
├── app/
│   ├── api/           # FastAPI endpoints
│   │   ├── admin.py   # Tenant management
│   │   ├── chats.py   # Conversation history
│   │   └── flows.py   # Flow definitions
│   ├── db/            # Database layer
│   │   ├── models.py  # SQLAlchemy models
│   │   ├── repository.py # Data access functions
│   │   └── types.py   # Custom types (encryption)
│   ├── services/      # Business logic
│   │   ├── tenant_service.py
│   │   └── chat_service.py
│   ├── core/          # Core framework
│   ├── flow_core/     # Conversation engine
│   └── whatsapp/      # WhatsApp integration
├── playground/        # Example flows
├── tests/            # Test files
└── config.json       # Multi-tenant configuration
```

## 🐛 Troubleshooting

### Common Issues

**Database Connection Error:**

```
sqlalchemy.exc.OperationalError: could not connect to server
```

- Check PostgreSQL is running: `brew services list | grep postgresql`
- Verify DATABASE_URL in .env
- Test connection: `psql chatai`

**Encryption Key Error:**

```
RuntimeError: PII_ENCRYPTION_KEY is required
```

- Generate key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- Add to .env: `PII_ENCRYPTION_KEY=your-key-here`

**Import Errors:**

```
ModuleNotFoundError: No module named 'app'
```

- Activate virtual environment: `source .venv/bin/activate`
- Install dependencies: `uv sync`

**Redis Connection Warning:**

```
Failed to initialize Redis store. Falling back to memory.
```

- This is OK for development
- Start Redis: `redis-server` or `brew services start redis`

### Debug Mode

```bash
# Enable debug logging
export DEBUG=true

# Or add to .env
echo "DEBUG=true" >> .env
```

### Reset Database

```bash
# Drop and recreate database
dropdb chatai
createdb chatai

# Restart server (tables auto-created)
uvicorn app.main:app --reload
```

## 🚀 Production Deployment

### Environment Differences

- Use proper PostgreSQL instance (not local)
- Set strong encryption key (store in secrets manager)
- Configure Redis cluster
- Set up proper logging
- Use HTTPS with SSL certificates
- Configure rate limiting

### Docker Deployment

```bash
# Build image
docker build -t chatai-backend .

# Run with docker-compose
docker-compose up -d
```

### Health Monitoring

- Health endpoint: `GET /health`
- Database connectivity check
- Redis connectivity check
- Monitor encryption key rotation

---

## 📚 Next Steps

1. **Read Architecture**: [ARCHITECTURE.md](./ARCHITECTURE.md)
2. **API Reference**: [API_DOCUMENTATION.md](./API_DOCUMENTATION.md)
3. **Set up Twilio**: Configure WhatsApp webhook
4. **Add Authentication**: Implement API keys
5. **Deploy**: Set up production environment

---

**Need Help?** Check the logs, they're comprehensive and will guide you to the issue!

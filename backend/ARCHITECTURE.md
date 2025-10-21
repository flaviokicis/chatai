# ChatAI Backend Architecture

A white-label WhatsApp inbox automation service built with FastAPI, SQLAlchemy, and PostgreSQL.

## 🏗️ System Overview

This is a **multi-tenant B2B SaaS platform** that enables businesses to automate their WhatsApp customer interactions through AI-powered conversation flows. Each tenant (customer) can configure their own flows, manage multiple WhatsApp numbers, and track all customer conversations with full GDPR/LGPD compliance.

### Core Value Proposition

- **White-label**: Each tenant appears as their own brand to end customers
- **Multi-channel**: Currently WhatsApp, designed for Instagram DM expansion
- **Flow-based**: Conversations follow predefined decision trees
- **Privacy-first**: All PII encrypted at rest, GDPR compliant
- **Enterprise-ready**: Proper logging, monitoring, rate limiting

## 🎯 Domain Model & Relationships

### Entity Relationship Overview

```
Tenant (1) ──→ (1) TenantProjectConfig
   │
   ├── (1) ──→ (*) ChannelInstance ──→ (*) Flow
   │                    │
   └── (1) ──→ (*) Contact ──→ (*) ChatThread ──→ (*) Message
                              │                      │
                              └── (1) ──→ (*) MessageAttachment
```

### Core Entities Explained

#### **Tenant** - The Customer Business

- **Purpose**: Represents each customer of your white-label service
- **Key Fields**: Owner contact info (encrypted), timestamps
- **Why**: Multi-tenancy isolation - each tenant's data is completely separate
- **Relationship**: Root entity that owns all other data

#### **TenantProjectConfig** - Business Context for AI

- **Purpose**: Stores business description, target audience, communication style
- **Why**: The AI needs context about the tenant's business to respond appropriately
- **Example**: "Fitness studio targeting professionals 25-45, friendly tone"
- **Relationship**: 1:1 with Tenant (could be embedded but separated for clarity)

#### **ChannelInstance** - Communication Endpoints

- **Purpose**: Represents each WhatsApp number or Instagram account
- **Key Fields**: `identifier` (e.g., "whatsapp:+14155238886"), phone number, provider metadata
- **Why**: Tenants may have multiple WhatsApp numbers for different purposes
- **Design Decision**: Generic enough to support Instagram DM later
- **Relationship**: Each tenant can have multiple channels

#### **Flow** - Conversation Logic

- **Purpose**: Stores the conversation decision tree as JSON
- **Key Fields**: `definition` (JSONB), `flow_id`, `is_active`
- **Why**: Business logic should be configurable without code changes
- **Format**: Compatible with existing flow engine (see `flow_core/`)
- **Relationship**: Each channel can have multiple flows (A/B testing, different purposes)

#### **Contact** - End Customer

- **Purpose**: Represents the people chatting with your tenant's business
- **Key Fields**: `external_id` (cross-platform), encrypted phone, consent tracking
- **GDPR Features**: Opt-in tracking, revocation, erasure requests
- **Why External ID**: Same person might contact via WhatsApp and Instagram
- **Relationship**: Belongs to tenant, can have multiple conversation threads

#### **ChatThread** - Conversation Session

- **Purpose**: Groups related messages into a conversation
- **Key Fields**: Status (open/closed/archived), last activity, metadata
- **Why**: WhatsApp conversations can span days/weeks - need logical grouping
- **Business Logic**: One thread per contact per channel (enforced by unique constraint)
- **Relationship**: Links contact to specific channel, contains all messages

#### **Message** - Individual Communication

- **Purpose**: Each WhatsApp message sent or received
- **Key Fields**: Direction, encrypted text, delivery status, timestamps
- **Why Encrypted**: PII compliance - message content is sensitive
- **Provider Integration**: Stores Twilio message IDs for delivery tracking
- **Relationship**: Belongs to thread, can have attachments

#### **MessageAttachment** - Media Files

- **Purpose**: Images, videos, documents sent via WhatsApp
- **Key Fields**: Media type, file URL, size, metadata
- **Why Separate**: Messages can have multiple attachments
- **Storage**: URLs point to cloud storage (S3, etc.)

## 🔧 Technical Architecture

### Layer Architecture

```
┌─────────────────────────────────────────┐
│              API Layer                  │  ← FastAPI endpoints
├─────────────────────────────────────────┤
│            Service Layer                │  ← Business logic
├─────────────────────────────────────────┤
│           Repository Layer              │  ← Data access
├─────────────────────────────────────────┤
│             ORM Layer                   │  ← SQLAlchemy models
├─────────────────────────────────────────┤
│            Database                     │  ← PostgreSQL
└─────────────────────────────────────────┘
```

### Design Patterns Used

#### **Repository Pattern**

- **Location**: `app/db/repository.py`
- **Purpose**: Abstracts database operations from business logic
- **Benefits**: Testable, swappable data sources, consistent query patterns
- **Example**: `get_threads_by_tenant()` handles complex joins and filtering

#### **Service Layer Pattern**

- **Location**: `app/services/`
- **Purpose**: Contains business logic and orchestrates repository calls
- **Benefits**: Transaction management, validation, error handling
- **Example**: `TenantService.create_tenant()` creates tenant + config atomically

#### **Dependency Injection**

- **Implementation**: FastAPI's `Depends()` system
- **Purpose**: Clean separation of concerns, testability
- **Example**: Database sessions injected into endpoints

#### **Domain-Driven Design (DDD)**

- **Aggregates**: Tenant is the aggregate root
- **Value Objects**: Enums for status, direction, etc.
- **Domain Events**: Could be added for webhook notifications

### Security Architecture

#### **Admin Authentication**

- Session-based admin authentication is provided for controller endpoints under `/api/controller/*`.
- Login via `POST /api/controller/auth` issues a session cookie with a 24h expiry; requires `ADMIN_PASSWORD` (and optional `ADMIN_USERNAME`).
- Rate limiting and cooldowns for admin login attempts use Redis when available; falls back to allowing attempts if Redis is unavailable.
- Admin-protected routes validate the session on each request.

#### **Encryption at Rest**

- **Implementation**: Custom `EncryptedString` SQLAlchemy type
- **Algorithm**: Fernet (AES-256-GCM) - symmetric encryption
- **Key Management**: Environment variable `PII_ENCRYPTION_KEY`
- **Encrypted Fields**: Emails, phone numbers, message text
- **Why**: GDPR/LGPD compliance, data breach protection

#### **Multi-Tenant Isolation**

- **Strategy**: Shared database, tenant-scoped queries
- **Implementation**: Every query includes `tenant_id` filter
- **Benefits**: Cost-effective, easier maintenance than separate DBs
- **Risk Mitigation**: Repository pattern ensures consistent filtering

#### **Soft Deletes**

- **Implementation**: `deleted_at` timestamp on all entities
- **Purpose**: GDPR "right to be forgotten" + audit trail
- **Query Pattern**: All queries filter `WHERE deleted_at IS NULL`

## 🔌 Integration Points

### WhatsApp Integration (Twilio / Cloud API)

- **Unified Webhook**: `POST /api/webhooks/whatsapp` (also mounts legacy `POST /api/webhooks/twilio/whatsapp` and non-`/api` legacy path for backward compatibility)
- **Flow**: Incoming message → Find channel → Create/update thread → Run AI → Reply
- **Persistence**: All messages automatically saved to database
- **Security**: Twilio signature validation

### AI/LLM Integration

- **Framework**: LangChain with provider-agnostic initialization (Google Gemini or OpenAI depending on settings)
- **Context**: Uses tenant project config for personalization
- **Flow Engine**: Custom decision tree engine in `flow_core/`
- **Conversation Memory**: Redis-backed session storage

### Future Integrations

- **Instagram DM**: Same `ChannelInstance` model, different `channel_type`
- **Webhooks**: Could add outbound webhooks for tenant notifications
- **Analytics**: Message/thread data ready for reporting

## 📊 Data Flow Examples

### New WhatsApp Message Flow

```
1. Twilio → POST /webhooks/twilio/whatsapp
2. Validate signature, parse message
3. Find ChannelInstance by phone number
4. Get/create Contact by sender
5. Get/create ChatThread
6. Save inbound Message
7. Run AI conversation flow
8. Save outbound Message
9. Send reply via Twilio
```

### Tenant Onboarding Flow

```
1. POST /admin/tenants (create tenant + config)
2. POST /admin/tenants/{id}/channels (add WhatsApp number)
3. POST /admin/tenants/{id}/flows (upload conversation flow)
4. Configure Twilio webhook → your domain
5. Ready to receive messages
```

## 🚀 Deployment Considerations

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db

# Encryption (CRITICAL - generate with Fernet.generate_key())
PII_ENCRYPTION_KEY=base64-encoded-32-byte-key

# LLM
# When llm_provider=openai
OPENAI_API_KEY=your-openai-key
# When llm_provider=google
GOOGLE_API_KEY=your-gemini-key

# Redis (optional, falls back to memory)
# Either redis_conn_url or redis_url is accepted
REDIS_URL=redis://localhost:6379/0
REDIS_CONN_URL=redis://localhost:6379/0

# Twilio
TWILIO_AUTH_TOKEN=your-token
PUBLIC_BASE_URL=https://your-domain.com
```

### Database Migrations

- **Current**: Auto-create tables on startup (dev only)
- **Production**: Use Alembic for proper migrations
- **Indexes**: Add indexes on `tenant_id`, `created_at`, `external_id`

### Scaling Considerations

- **Database**: Read replicas for analytics queries
- **Redis**: Cluster mode for high availability
- **API**: Horizontal scaling (stateless design)
- **File Storage**: S3 for message attachments

## 🔍 Monitoring & Observability

### Logging Strategy

- **Structured Logging**: JSON format with correlation IDs
- **Levels**: INFO for business events, ERROR for failures
- **Context**: Always include `tenant_id` for filtering
- **PII**: Never log encrypted content

### Key Metrics to Track

- **Business**: Messages/day per tenant, conversation completion rates
- **Technical**: API response times, database query performance
- **Security**: Failed authentication attempts, encryption key rotations

### Health Checks

- **Database**: Connection pool status
- **Redis**: Store connectivity (falls back to in-memory)
- **External APIs**: Twilio/WhatsApp Cloud, LLM provider availability

## 🔮 Future Enhancements

### Authentication (Next Priority)

- **API Keys**: Tenant-scoped keys for programmatic access
- **Admin Dashboard**: JWT-based authentication
- **RBAC**: Role-based permissions (admin, read-only, etc.)

### Advanced Features

- **Analytics Dashboard**: Conversation metrics, sentiment analysis
- **A/B Testing**: Multiple flows per channel with traffic splitting
- **Webhook System**: Real-time notifications to tenant systems
- **Multi-language**: Flow translations, language detection

### Technical Improvements

- **Event Sourcing**: Audit trail of all changes
- **CQRS**: Separate read/write models for performance
- **GraphQL**: More flexible API for complex queries
- **Microservices**: Split by domain (auth, messaging, analytics)

---

This architecture balances **simplicity** (easy to understand and maintain) with **scalability** (can grow to millions of messages) while maintaining **security** (GDPR compliant) and **flexibility** (easy to add new channels and features).

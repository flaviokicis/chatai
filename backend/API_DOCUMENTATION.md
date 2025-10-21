# ChatAI API Documentation

Complete API reference for the white-label WhatsApp automation platform.

## 🚀 Getting Started

### Base URL

```
http://localhost:8080  # Development
https://your-domain.com  # Production
```

### Interactive Documentation

- **Swagger UI**: `http://localhost:8080/docs`
- **ReDoc**: `http://localhost:8080/redoc`

### Authentication

- Admin Controller endpoints (`/api/controller/*`) require session-based login via `POST /api/controller/auth`. Set `ADMIN_PASSWORD` in the environment. A session cookie is issued and must be sent on subsequent requests.
- Public endpoints (`/api/tenants`, `/api/channels`, `/api/chats`, `/api/flows`, `/api/webhooks/*`) are open unless otherwise noted.

### Global API Prefix

All application endpoints are mounted under the global prefix `/api`. Paths shown below are relative to this prefix unless otherwise specified.

## 📋 API Overview

### Endpoint Categories

| Category             | Prefix                            | Purpose                                        |
| -------------------- | --------------------------------- | ---------------------------------------------- |
| **Admin Controller** | `/controller`                     | Admin login; tenant/channel/flow management    |
| **Public Tenants**   | `/tenants`                        | Public tenant and flow listings                 |
| **Channels**         | `/channels`                       | Channel instances and associated flows          |
| **Chats**            | `/chats`                          | Conversation history, contact management        |
| **Flows**            | `/flows`                          | Flow compilation and example flows              |
| **Documents**        | `/tenants/{tenant_id}/documents`  | RAG documents upload, status, and clearing      |
| **Webhooks**         | `/webhooks`                       | External integrations (WhatsApp/Twilio/Cloud)   |

---

## 🏢 Admin Controller (`/controller`)

Manage tenants, channels, and conversation flows.

### Admin Login

```http
POST /api/controller/auth
```

Authenticates an admin user and issues a session cookie (required for all controller endpoints).

### Create Tenant

```http
POST /api/controller/tenants
```

Creates a new tenant with project configuration.

**Request Body:**

```json
{
  "first_name": "John",
  "last_name": "Doe",
  "email": "john@fitness-studio.com",
  "project_description": "Premium fitness studio offering personal training and group classes",
  "target_audience": "Professionals aged 25-45 who value efficiency and results",
  "communication_style": "Friendly but professional, focus on health benefits"
}
```

**Response:**

```json
{
  "id": 1,
  "first_name": "John",
  "last_name": "Doe",
  "email": "john@fitness-studio.com"
}
```

**Business Logic:**

- Email is encrypted at rest
- Project config helps AI understand business context
- Atomic operation (tenant + config created together)

---

### List Tenants

```http
GET /api/controller/tenants
```

Returns all active tenants (soft-deleted tenants excluded).

**Response:**

```json
[
  {
    "id": 1,
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@fitness-studio.com"
  }
]
```

---

### Create Channel Instance

```http
POST /api/controller/tenants/{tenant_id}/channels
```

Adds a WhatsApp number or Instagram account to a tenant.

**Request Body:**

```json
{
  "channel_type": "whatsapp",
  "identifier": "whatsapp:+14155238886",
  "phone_number": "+14155238886",
  "extra": {
    "twilio_sid": "AC...",
    "webhook_secret": "..."
  }
}
```

**Response:**

```json
{
  "id": 1,
  "channel_type": "whatsapp",
  "identifier": "whatsapp:+14155238886",
  "phone_number": "+14155238886"
}
```

**Key Concepts:**

- `identifier`: Unique cross-platform ID (used for webhook routing)
- `phone_number`: Convenience field (encrypted)
- `extra`: Provider-specific metadata (Twilio SIDs, secrets, etc.)

---

### List Channel Instances

```http
GET /api/controller/tenants/{tenant_id}/channels
```

Returns all channels for a tenant.

**Response:**

```json
[
  {
    "id": 1,
    "channel_type": "whatsapp",
    "identifier": "whatsapp:+14155238886",
    "phone_number": "+14155238886"
  }
]
```

---

### Create Flow

```http
POST /api/controller/tenants/{tenant_id}/flows
```

Uploads a conversation flow definition.

**Request Body:**

```json
{
  "name": "Sales Qualification Flow",
  "flow_id": "sales_qualifier_v1",
  "channel_instance_id": 1,
  "definition": {
    "schema_version": "v2",
    "id": "flow.sales_qualifier",
    "entry": "q.intention",
    "nodes": [
      {
        "id": "q.intention",
        "kind": "Question",
        "key": "intention",
        "prompt": "Como posso te ajudar hoje?"
      }
    ],
    "edges": []
  }
}
```

**Response:**

```json
{
  "id": 1,
  "name": "Sales Qualification Flow",
  "flow_id": "sales_qualifier_v1",
  "channel_instance_id": 1
}
```

**Flow Definition Format:**

- Compatible with existing `flow_core` engine
- JSONB storage for flexibility
- Versioned schema for migrations

---

### List Flows

```http
GET /api/controller/tenants/{tenant_id}/flows
```

Returns all flows for a tenant.

---

## 💬 Chat API (`/chats`)

Access conversation history and manage contacts.

### List Chat Threads

```http
GET /api/chats/tenants/{tenant_id}/threads?channel_instance_id=1&limit=50&offset=0
```

Returns paginated list of conversations.

**Query Parameters:**

- `channel_instance_id` (optional): Filter by WhatsApp number
- `limit`: Max results (1-200, default 50)
- `offset`: Pagination offset (default 0)

**Response:**

```json
[
  {
    "id": 1,
    "status": "open",
    "subject": null,
    "last_message_at": "2024-01-15T10:30:00Z",
    "created_at": "2024-01-15T09:00:00Z",
    "contact": {
      "id": 1,
      "external_id": "whatsapp:+5511999999999",
      "display_name": "Maria Silva",
      "phone_number": "+5511999999999",
      "created_at": "2024-01-15T09:00:00Z",
      "consent_opt_in_at": "2024-01-15T09:00:00Z",
      "consent_revoked_at": null
    }
  }
]
```

**Business Logic:**

- Ordered by `last_message_at` (most recent first)
- Includes contact info for display
- GDPR consent status visible

---

### Get Thread Detail

```http
GET /api/chats/tenants/{tenant_id}/threads/{thread_id}
```

Returns complete conversation with all messages.

**Response:**

```json
{
  "id": 1,
  "status": "open",
  "subject": null,
  "last_message_at": "2024-01-15T10:30:00Z",
  "created_at": "2024-01-15T09:00:00Z",
  "contact": {
    /* same as above */
  },
  "messages": [
    {
      "id": 1,
      "direction": "inbound",
      "status": "delivered",
      "text": "Olá, gostaria de saber sobre os planos",
      "created_at": "2024-01-15T09:00:00Z",
      "sent_at": "2024-01-15T09:00:00Z",
      "delivered_at": "2024-01-15T09:00:01Z",
      "read_at": null,
      "provider_message_id": "SM..."
    },
    {
      "id": 2,
      "direction": "outbound",
      "status": "sent",
      "text": "Olá! Ficamos felizes com seu interesse...",
      "created_at": "2024-01-15T09:01:00Z",
      "sent_at": "2024-01-15T09:01:00Z",
      "delivered_at": null,
      "read_at": null,
      "provider_message_id": null
    }
  ]
}
```

**Message Fields Explained:**

- `direction`: "inbound" (customer) or "outbound" (business)
- `status`: Delivery status from WhatsApp
- `text`: Decrypted message content
- `provider_message_id`: Twilio message ID for tracking

---

### List Contacts

```http
GET /api/chats/tenants/{tenant_id}/contacts?limit=100&offset=0
```

Returns all contacts for a tenant.

**Response:**

```json
[
  {
    "id": 1,
    "external_id": "whatsapp:+5511999999999",
    "display_name": "Maria Silva",
    "phone_number": "+5511999999999",
    "created_at": "2024-01-15T09:00:00Z",
    "consent_opt_in_at": "2024-01-15T09:00:00Z",
    "consent_revoked_at": null
  }
]
```

---

### Update Thread Status

```http
PATCH /api/chats/tenants/{tenant_id}/threads/{thread_id}/status
```

Changes conversation status (open/closed/archived).

**Request Body:**

```json
{
  "status": "closed"
}
```

**Response:**

```json
{
  "status": "updated"
}
```

**Use Cases:**

- Close resolved conversations
- Archive old conversations
- Reopen conversations if customer replies

---

### Update Contact Consent

```http
POST /api/chats/tenants/{tenant_id}/contacts/{contact_id}/consent
```

Manages GDPR/LGPD consent status.

**Request Body:**

```json
{
  "action": "opt_in" // "opt_in", "revoke", "request_erasure"
}
```

**Response:**

```json
{
  "status": "updated",
  "action": "opt_in"
}
```

**GDPR Compliance:**

- `opt_in`: Customer consents to data processing
- `revoke`: Customer withdraws consent
- `request_erasure`: Customer requests data deletion

---

## 🌊 Flow API (`/flows`)

Manage conversation flow definitions.

### Get Example Flow (Raw)

```http
GET /api/flows/example/raw
```

Returns the example flow JSON from `playground/flow_example.json`.

### Get Example Flow (Compiled)

```http
GET /api/flows/example/compiled
```

---

## 📄 Documents API (`/tenants/{tenant_id}/documents`)

Manage tenant documents for Retrieval-Augmented Generation (RAG).

### Upload Document

```http
POST /api/tenants/{tenant_id}/documents/upload
```

Uploads and processes a document (PDF, TXT, MD, JSON) for retrieval.

### Document Status

```http
GET /api/tenants/{tenant_id}/documents/status
```

Checks if the tenant has any processed documents.

### Clear Documents

```http
DELETE /api/tenants/{tenant_id}/documents/clear
```

Deletes all documents and embeddings for the tenant.

Returns the flow compiled by the flow engine (ready for execution).

---

## 🔗 Webhook API (`/webhooks`)

External system integrations.

### WhatsApp Webhooks

Primary unified endpoint (supports Twilio and Cloud API):

```http
POST /api/webhooks/whatsapp
```

Legacy Twilio-compatible endpoint (also available without `/api` prefix for backwards compatibility):

```http
POST /api/webhooks/twilio/whatsapp
POST /webhooks/twilio/whatsapp
```

**Headers:**

- `X-Twilio-Signature`: Signature for validation

**Request Body:** (Twilio format)

```
From=whatsapp:+5511999999999
To=whatsapp:+14155238886
Body=Olá, gostaria de saber sobre os planos
MessageSid=SM...
```

**Response:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>Olá! Ficamos felizes com seu interesse...</Message>
</Response>
```

**Processing Flow:**

1. Validate Twilio signature
2. Find channel instance by `To` number
3. Get/create contact by `From` number
4. Get/create conversation thread
5. Save inbound message
6. Run AI conversation flow
7. Save outbound message
8. Return TwiML response

---

## 🔧 System Endpoints

### Health Check

```http
GET /health
```

**Response:**

```
ok
```

Simple health check for load balancers.

---

## 📊 Error Handling

### Standard Error Format

```json
{
  "detail": "Tenant 999 not found"
}
```

### HTTP Status Codes

| Code  | Meaning      | When                                          |
| ----- | ------------ | --------------------------------------------- |
| `200` | Success      | Request completed successfully                |
| `400` | Bad Request  | Invalid input data                            |
| `404` | Not Found    | Resource doesn't exist                        |
| `409` | Conflict     | Duplicate resource (e.g., channel identifier) |
| `500` | Server Error | Unexpected system error                       |

### Common Error Scenarios

**Tenant Not Found (404):**

```json
{
  "detail": "Tenant 123 not found"
}
```

**Duplicate Channel (409):**

```json
{
  "detail": "Channel identifier already exists"
}
```

**Validation Error (400):**

```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## 🚀 Usage Examples

### Complete Tenant Setup

```bash
# 1. Admin login (get session cookie)
curl -i -X POST http://localhost:8080/api/controller/auth \
  -H "Content-Type: application/json" \
  -d '{"password": "${ADMIN_PASSWORD}"}'

# 2. Create tenant (send Cookie header from previous response)
curl -X POST http://localhost:8080/api/controller/tenants \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@fitness.com",
    "project_description": "Premium fitness studio",
    "target_audience": "Professionals 25-45",
    "communication_style": "Friendly but professional"
  }'

# 3. Add WhatsApp number
curl -X POST http://localhost:8080/api/controller/tenants/1/channels \
  -H "Content-Type: application/json" \
  -d '{
    "channel_type": "whatsapp",
    "identifier": "whatsapp:+14155238886",
    "phone_number": "+14155238886"
  }'

# 4. Upload conversation flow
curl -X POST http://localhost:8080/api/controller/tenants/1/flows \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sales Flow",
    "flow_id": "sales_v1",
    "channel_instance_id": 1,
    "definition": { /* flow JSON */ }
  }'
```

### Monitor Conversations

```bash
# List recent conversations
curl http://localhost:8080/api/chats/tenants/1/threads?limit=10

# Get conversation detail
curl http://localhost:8080/api/chats/tenants/1/threads/1

# Close conversation
curl -X PATCH http://localhost:8080/api/chats/tenants/1/threads/1/status \
  -H "Content-Type: application/json" \
  -d '{"status": "closed"}'
```

---

## 🔮 Planned Features

### Authentication (Coming Soon)

```http
# API Key authentication
Authorization: Bearer sk_tenant_abc123...

# JWT for admin dashboard
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

### Advanced Endpoints (Roadmap)

- `GET /analytics/tenants/{id}/metrics` - Conversation analytics
- `POST /flows/{id}/test` - Test flow with sample input
- `GET /contacts/{id}/history` - Cross-channel contact history
- `POST /messages/{id}/retry` - Retry failed message delivery

---

This API is designed for **high-volume production use** with proper error handling, validation, and scalability considerations. All endpoints are stateless and can be horizontally scaled.

## Inboxed — AI Inbox Automation

Inboxed is an inbox automation tool that uses AI agents to triage, qualify, and resolve customer conversations across messaging channels. Today we focus on WhatsApp Business; the design is multichannel (e.g., Instagram DMs) and multitenant from day one.

### What it does

- **AI agents**: Handle conversational checklists (e.g., sales qualification) with extraction, policy, and human-handoff.
- **WhatsApp Business API**: Webhook-powered ingestion and responses via Twilio (for dev) with signature validation.
- **Multichannel-ready**: Architecture supports multiple inbox types per tenant; WhatsApp is implemented first.
- **Human handoff**: Seamless escalation paths when automation confidence is low.

### Repo structure

- `backend/` — FastAPI service exposing WhatsApp webhook endpoints, agent runtime, and configuration provider.
- `frontend/` — Next.js app with Tailwind and shadcn/ui for the operator experience (demo home included).

### Quickstart

Backend (FastAPI):

```bash
cd /Users/jessica/me/chatai/backend
uv venv
source .venv/bin/activate
uv sync
cp env.example .env
# set TWILIO_AUTH_TOKEN and optional PUBLIC_BASE_URL
CONFIG_JSON_PATH=./config.local.json uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
# Health: http://localhost:8080/health
```

Frontend (Next.js):

```bash
cd /Users/jessica/me/chatai/frontend
pnpm install
pnpm dev
# App: http://localhost:3000
```

### Product notes

- We avoid hardcoding customer specifics; all agent behavior is fed by configurable graphs and prompts.
- Whenever choosing between hardcoded string heuristics (ifs/switch on phrases) and an LLM instruction, prefer using the LLM to decide behavior.
- WhatsApp is the initial channel. Additional channels (e.g., Instagram) fit the same configuration surface.
- The demo home in the frontend shows how a logged-in operator would view inboxes, conversations, and agent status using our brand colors.

### Language

- User-facing content is Portuguese (Brazil). LLM prompts that produce messages visible to end users, plus UI labels, are in PT-BR. Internal/decision-making prompts can remain in English.
- Example flows/configs updated with PT-BR prompts: `backend/config.json`, `backend/config.local.json`, and `backend/playground/flow_example.json`.

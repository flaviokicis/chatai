# Chatai Backend (FastAPI + Twilio WhatsApp Webhook)

This service exposes a FastAPI endpoint to receive Twilio WhatsApp webhooks with signature verification.

## Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) installed
- A public URL for local dev (e.g. ngrok or Cloudflare Tunnel)
- Your Twilio Account Auth Token

## Setup

```bash
cd /Users/jessica/me/chatai/backend
uv venv
source .venv/bin/activate
uv sync
cp env.example .env
# Edit .env and set TWILIO_AUTH_TOKEN and optionally PUBLIC_BASE_URL
```

## Run

```bash
cd /Users/jessica/me/chatai/backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

- Local health check: `http://localhost:8080/health`
- Webhook endpoint: `POST http://localhost:8080/webhooks/twilio/whatsapp`

## Configure Twilio

1. Create a public tunnel, e.g. with ngrok:
   ```bash
   ngrok http http://localhost:8080
   ```
2. Set `PUBLIC_BASE_URL` in `.env` to the tunnel URL (without the trailing slash).
3. In Twilio Console, set your WhatsApp inbound message webhook to:
   ```
   https://YOUR_PUBLIC_BASE_URL/webhooks/twilio/whatsapp
   ```
4. Choose HTTP `POST` and `application/x-www-form-urlencoded`.

## Notes

- The webhook validates `X-Twilio-Signature`. Requests failing validation return `403`.
- For JSON payloads, raw body validation is used automatically.
- Keep handler fast; do heavy work in background tasks or a queue.

## Test-driven development (TDD)

This project is intentionally run with a pragmatic TDD mindset:

- **Impact first (Pareto)**: we cover the most business-critical paths first rather than chasing 100% coverage.
- **Useful, meaningful tests**: tests document behavior and prevent regressions; they are not busywork.
- **Fast feedback**: unit and lightweight integration tests should run quickly.
- **Evolving tests**: as requirements change, tests evolve to reflect intended behavior.

Run tests:

```bash
cd /Users/jessica/me/chatai/backend
source .venv/bin/activate
uv run pytest -q
```

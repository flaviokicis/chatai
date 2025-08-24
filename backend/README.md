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
cp config.json config.local.json # optional: override per environment
```

## Run

```bash
cd /Users/jessica/me/chatai/backend
source .venv/bin/activate
CONFIG_JSON_PATH=./config.local.json uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

- Local health check: `http://localhost:8080/health`
- Webhook endpoint: `POST http://localhost:8080/webhooks/twilio/whatsapp`

## Logging

The backend uses structured logging configured in `app.core.logging`. Output is
formatted as key-value pairs and includes a `request_id` field for each HTTP
request. The request ID comes from the `X-Request-ID` header when supplied or is
generated automatically and echoed back in responses. Adjust verbosity with the
`LOG_LEVEL` environment variable (default: `INFO`).

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

## Multitenant configuration (temporary JSON-backed)

This project is multitenant. On startup we load a tenant configuration provider that can be swapped later without code changes.

- Abstract provider: `app/config/provider.py` (`ConfigProvider`, `TenantAgentConfig`)
- JSON implementation: `app/config/loader.py` loads a JSON file into a `ConfigProvider`
- Default config location: `./config.json` (override with env `CONFIG_JSON_PATH`)

Schema (temporary):

```json
{
  "default": {
    "enabled_agents": ["sales_qualifier"],
    "channels": [
      {
        "channel_type": "whatsapp",
        "channel_id": "whatsapp:+15551112222",
        "enabled_agents": ["sales_qualifier"],
        "default_instance_id": "sq_default",
        "agent_instances": [
          {
            "instance_id": "sq_default",
            "agent_type": "sales_qualifier",
            "params": {
              "question_graph": [
                {
                  "key": "intention",
                  "prompt": "What is your intention?",
                  "priority": 10
                }
              ]
            },
            "handoff": { "target": "sales_slack" }
          }
        ]
      }
    ]
  },
  "tenants": {
    "TENANT_ID": {
      "enabled_agents": ["sales_qualifier"],
      "channels": [
        {
          "channel_type": "whatsapp",
          "channel_id": "whatsapp:+15559998888",
          "enabled_agents": ["sales_qualifier"],
          "default_instance_id": "sq_default",
          "agent_instances": [
            {
              "instance_id": "sq_default",
              "agent_type": "sales_qualifier",
              "params": {
                "question_graph": [
                  {
                    "key": "intention",
                    "prompt": "What is your intention?",
                    "priority": 10
                  }
                ]
              },
              "handoff": { "target": "sales_slack" }
            }
          ]
        }
      ]
    }
  }
}
```

Notes:

- `channel_type` + `channel_id` uniquely identify a channel instance. For WhatsApp, `channel_id` can be the Twilio WhatsApp sender like `whatsapp:+15551112222`.
- Per-channel `enabled_agents` override tenant defaults, allowing multiple WhatsApp inboxes per tenant with different agents.
- Each channel may define `agent_instances` and a `default_instance_id`. An agent instance carries human configuration (e.g., question graph, prompts, validation, and handoff routing).
- For now we only support the `sales_qualifier` agent. In production, this JSON will be replaced with a Postgres-backed configuration while preserving the `ConfigProvider` interface.

## Playground JSONs

Sample question graph payloads are available under `backend/playground/`:

- `sales_qualifier_question_graph_basic.json`: minimal 3-question flow
- `sales_qualifier_question_graph_full.json`: fuller sales qualifier checklist with dependencies

You can quickly test by pointing `CONFIG` to a file containing one of these payloads merged under your desired structure, or by using them as the `params` for a `sales_qualifier` agent instance.

### Testing and validation of configuration

- There are unit tests for configuration parsing and validation: see `tests/test_config.py`.
- When adding new configuration fields, always add/update tests first. Invalid configuration should cause tests to fail before runtime errors.
- The loader performs basic validation and raises `ValueError` on schema shape violations.

## Agent design guidance

- Prefer thin, logic-focused agents. State management, extraction, and next-question policy are provided by base components.
- Use Flow Core (`app.flow_core`) for all state machine logic. Agents should delegate progression to Engine and keep only domain glue logic.
- Use shared tool schemas from `app/flow_core/tool_schemas.py`.

### Principle: Prefer LLM reasoning over hardcoded keyword heuristics

- Whenever choosing between hardcoding behavior with if/switch and string keyword lists versus asking the LLM, prefer the LLM.
- Do not enumerate ad-hoc phrases (e.g., clarification or frustration keywords) to detect intent; ask the LLM with a targeted instruction instead.
- Avoid post-processing user-visible strings with brittle replacements. If phrasing needs adjustment, guide the LLM via instructions and constraints.
- Rationale: keeps behavior adaptable across languages and phrasing, reduces false positives/negatives, and centralizes behavior in model prompts.

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

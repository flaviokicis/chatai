# WhatsApp Simulator CLI

## Overview

The WhatsApp Simulator CLI (`whatsapp_cli.py`) is a command-line tool that simulates WhatsApp Business messaging behavior using the **exact same infrastructure** as the production webhook. Unlike the old CLIs that directly manipulated `FlowTurnRunner`, this simulator properly uses all production services.

## Key Features

✅ **Production Infrastructure**
- Uses `FlowProcessor` service (same as webhook)
- Database persistence for all messages, threads, contacts
- Redis session management for chat history
- Proper tenant and channel configuration
- Message logging and deduplication

✅ **WhatsApp-like Behavior**
- Async message queue - can type while bot is processing
- Typing indicators when bot is thinking
- Message delays simulation
- Persistent conversation history across sessions

✅ **Smart Design**
- Reuses existing tenant/channel/flow on restart (via `.whatsapp_cli_config.json`)
- Creates necessary DB records automatically
- Integrates with existing project context and tenant configs

## Architecture

```
User Input → Message Queue → FlowProcessor → Database/Redis
                ↓                  ↓              ↓
           Async Processing   Same as Webhook  Persistent
```

The CLI uses `FlowProcessor` directly (bypassing the WhatsApp-specific adapter layer) but maintains all the proper infrastructure:

1. **Database Setup**: Creates/reuses tenant, channel, flow, contact, thread
2. **Redis Sessions**: Uses `RedisSessionManager` for chat history
3. **FlowProcessor**: Same service used by webhook (not direct `FlowTurnRunner`)
4. **Message Persistence**: All messages saved to database

## Usage Modes

The WhatsApp CLI now supports three modes of operation:

### 1. Production Mode - Connect to Existing WhatsApp Channels

Connect to actual WhatsApp Business numbers configured in your database:

```bash
# List available channels
python -m app.flow_core.whatsapp_cli --list-channels

# Connect to a specific WhatsApp Business number
python -m app.flow_core.whatsapp_cli --phone +1234567890

# Connect with a custom flow override
python -m app.flow_core.whatsapp_cli --phone +1234567890 --flow playground/flow.json

# Specify your phone number
python -m app.flow_core.whatsapp_cli --phone +1234567890 --user-phone +9876543210
```

### 2. Test Mode - Create Isolated Test Environment

Create a new test tenant/channel for development:

```bash
# Create test environment with flow
python -m app.flow_core.whatsapp_cli playground/flow_example.json

# Reset and create new test environment
python -m app.flow_core.whatsapp_cli playground/flow_example.json --reset
```

### 3. Legacy Mode - Reuse Saved Configuration

Automatically reuses `.whatsapp_cli_config.json` if it exists:

```bash
# Reuses existing test configuration
python -m app.flow_core.whatsapp_cli playground/flow_example.json
```

### Command Options

| Option | Description |
|--------|-------------|
| `--phone NUMBER` | Connect to existing WhatsApp Business number |
| `--flow PATH` | Flow JSON file (optional with --phone) |
| `--model MODEL` | LLM model (default: gpt-5) |
| `--user-phone NUMBER` | Your phone number (default: +19995551234) |
| `--reset` | Reset config and create new test environment |
| `--list-channels` | List available WhatsApp channels |

### Examples

```bash
# Production use - connect to real WhatsApp channel
python -m app.flow_core.whatsapp_cli --phone 674436192430525

# Development - test a specific flow
python -m app.flow_core.whatsapp_cli playground/fluxo_luminarias.json

# Testing - override production flow
python -m app.flow_core.whatsapp_cli --phone +14155238886 --flow playground/new_flow.json
```

### Configuration

The CLI creates a `.whatsapp_cli_config.json` file that stores:
- Tenant ID
- Channel ID  
- Flow ID
- Phone numbers
- Creation timestamp

This allows the CLI to reuse the same database records across sessions, maintaining conversation history.

### Requirements

- PostgreSQL database (for tenant, channel, flow, messages)
- Redis server (for session management)
- OpenAI API key (for GPT models) or Anthropic API key (for Claude)
- `.env` file with proper configuration

## Differences from Old CLIs

| Feature | Old CLIs (deleted) | New WhatsApp CLI |
|---------|-------------------|------------------|
| Architecture | Direct `FlowTurnRunner` | `FlowProcessor` service |
| Database | None | Full persistence |
| Redis | None | Session management |
| Messages | In-memory only | Database storage |
| Tenant/Channel | None | Proper setup |
| Production Parity | Low | High |

## Testing

Use the provided test script:

```bash
cd backend
./test_whatsapp_cli.sh
```

## Implementation Details

The CLI simulates WhatsApp by:

1. **Database Layer**
   - Creates tenant with WhatsApp configuration
   - Sets up channel instance with phone number
   - Loads flow definition from JSON
   - Creates contact and thread for conversation

2. **Service Layer**
   - Initializes `FlowProcessor` with LLM and Redis
   - Uses `FlowRequest` objects (same as webhook)
   - Processes through same pipeline as production

3. **Message Flow**
   - User input → Message queue
   - Queue → `FlowProcessor.process_flow()`
   - Response → Database + Display
   - Supports typing while processing (async)

4. **Session Management**
   - Redis stores conversation history
   - Sessions keyed by user ID + flow ID
   - Persists across CLI restarts

## Main Challenges Solved

1. ✅ **Database Integration** - Proper tenant/channel/flow setup
2. ✅ **Redis Sessions** - Using `RedisSessionManager` like production
3. ✅ **Service Architecture** - `FlowProcessor` instead of direct runner
4. ✅ **Async Messaging** - Queue-based like WhatsApp
5. ✅ **Message Persistence** - All messages saved to DB
6. ✅ **Configuration Reuse** - Smart config file for persistence
7. ✅ **Production Channel Support** - Can connect to existing WhatsApp channels
8. ✅ **Import Conflict Resolution** - Renamed `types.py` to `flow_types.py`

## Future Enhancements

- [ ] Support for multiple concurrent conversations
- [ ] WhatsApp media message simulation
- [ ] Integration with actual WhatsApp Business API for testing
- [ ] Web UI for viewing conversation history
- [ ] Support for handoff scenarios

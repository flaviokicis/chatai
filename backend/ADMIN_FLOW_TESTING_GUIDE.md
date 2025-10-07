# Admin Flow Testing Guide

## Overview

This guide explains how to test the admin flow modification system, including both flow modifications and communication style changes.

## The System

### How It Works

The admin system has two main features:

1. **Flow Modification**: Admins can modify the flow structure during conversations
   - Examples: "Change this question to...", "Add a question about...", "Split this into 2 questions"
   - Uses the `modify_flow` action
   - Calls `FlowModificationExecutor` which uses the FlowChatService/FlowChatAgent

2. **Communication Style Changes**: Admins can adjust how the bot communicates
   - Examples: "Ta muito emoji, da uma maneirada", "Fale mais profissional", "Use menos emojis"
   - Uses the `update_communication_style` action
   - Handled by `CommunicationStyleExecutor`
   - **Appends** to the tenant's `communication_style` field (doesn't replace)

### Admin Detection

The system automatically detects admin users by:
1. Checking if the user's phone number is in `Tenant.admin_phone_numbers`
2. Using `AdminPhoneService.is_admin_phone()` for verification
3. Adding admin-specific instructions to the LLM prompt when admin is detected

### Confirmation Pattern

For safety, admin commands follow a **confirmation pattern**:
1. Admin: "Ta muito emoji, da uma maneirada"
2. Bot: "Entendi! Vou ajustar o estilo para usar menos emojis. Posso fazer essa alteração?"
3. Admin: "Sim" or "Confirmo"
4. Bot: Executes the action and confirms

## Testing Tools

### 1. Admin Flow CLI (Recommended) ⭐

Interactive CLI tool for testing admin commands **using the actual production responder**:

```bash
# First time - set up test environment
python admin_flow_cli.py --flow-file playground/flow_example.json

# Use existing configuration
python admin_flow_cli.py

# Use specific tenant and flow
python admin_flow_cli.py --tenant-id UUID --flow-id UUID --admin-phone +5511999999999

# Reset configuration and start fresh
python admin_flow_cli.py --reset
```

**Features:**
- ⭐ **Calls `EnhancedFlowResponder.respond()` directly** - same code as production!
- Tests the actual admin instructions from the prompt (lines 639-852 in responder.py)
- Interactive conversation with the flow
- Test admin commands in real-time
- See communication style changes with `style` command
- Type `reset` to restart flow from beginning
- View action execution results and collected data
- Saved configuration for easy re-use

**Why this is the best tool:**
- No code duplication - tests the real system
- Includes all admin instructions from the production prompt
- Shows exactly how admins interact in production
- Debug info shows tool calls, confidence, reasoning

### 2. Direct Testing via Python

```python
from uuid import UUID
from app.db.session import create_session
from app.services.admin_phone_service import AdminPhoneService
from app.core.flow_processor import FlowProcessor
from app.core.models import FlowRequest, ProjectContext
from app.core.llm import create_llm_client

# Set up admin phone
tenant_id = UUID("your-tenant-id")
admin_phone = "+5511999999999"

with create_session() as session:
    admin_service = AdminPhoneService(session)
    admin_service.add_admin_phone(admin_phone, tenant_id)
    session.commit()

# Process admin command
llm_client = create_llm_client()
processor = FlowProcessor(llm_client)

request = FlowRequest(
    user_id=f"whatsapp:{admin_phone}",
    tenant_id=tenant_id,
    message="Ta muito emoji, da uma maneirada",
    channel_type="whatsapp",
    project_context=ProjectContext(...),
    flow_metadata={...}
)

response = await processor.process_flow(request, app_context=None)
print(response.message)
```

### 3. WhatsApp CLI (End-to-End Testing)

Test the full WhatsApp integration:

```bash
# Connect as admin user
python whatsapp_cli.py --phone +14155238886 --user-phone +5511999999999
```

Then send admin commands through the CLI to test the full flow.

## Test Scenarios

### Scenario 1: Communication Style Reduction (Your Example)

**Setup:**
- Admin is testing the bot as a customer
- They notice too many emojis

**Test:**
```
Admin: "Oi! Quero saber sobre os produtos"
Bot: "Olá! 😊 Que legal! 🎉 Vamos te ajudar! ✨"
Admin: "Ta muito emoji, da uma maneirada"
Bot: "Entendi! Vou ajustar o estilo de comunicação para usar menos emojis. Posso fazer essa alteração?"
Admin: "Sim"
Bot: "Perfeito! ✅ Estilo de comunicação atualizado!"
```

**What happens:**
1. Bot detects admin command: "Ta muito emoji, da uma maneirada"
2. Matches communication style trigger pattern
3. Asks for confirmation
4. On confirmation, calls `CommunicationStyleExecutor`
5. Appends instruction to tenant's `communication_style` field:
   ```
   Original: "Friendly and professional"
   Updated: "Friendly and professional\n\nUse menos emojis. Evite excesso de emojis nas mensagens."
   ```
6. Future messages will follow the updated style

**Verification:**
```python
# Check updated style
with create_session() as session:
    tenant = get_tenant_by_id(session, tenant_id)
    print(tenant.project_config.communication_style)
```

### Scenario 2: Flow Modification

**Test:**
```
Admin: "Change this question to ask for full name instead of just first name"
Bot: "Entendi! Vou alterar esta pergunta para solicitar o nome completo. Confirma essa modificação?"
Admin: "Sim"
Bot: "Perfeito! Estou processando a alteração no fluxo..."
```

**What happens:**
1. Bot detects flow modification command
2. Asks for confirmation
3. On confirmation, calls `FlowModificationExecutor`
4. Executor calls `FlowChatService.send_user_message(flow_id, instruction)`
5. FlowChatAgent modifies the flow structure
6. Changes persist to database

### Scenario 3: Admin Testing Normal Flow

**Question:** What if admin wants to test the flow as a customer would see it?

**Answer:** Currently, there's no "incognito mode" for admins. If you're an admin, the system will always:
1. Add admin instructions to the prompt
2. Enable admin actions (modify_flow, update_communication_style)
3. Detect admin commands

**Workaround:**
- Use a different phone number (non-admin) to test as a customer
- Or temporarily remove your phone from admin list:
  ```python
  admin_service.remove_admin_phone("+5511999999999", tenant_id)
  ```

## Common Issues

### Issue 1: Admin Commands Not Detected

**Symptoms:** Bot treats admin commands as normal conversation

**Causes:**
- Phone number not in `admin_phone_numbers` list
- Phone format mismatch (e.g., with/without `whatsapp:` prefix)

**Solution:**
```python
# Check admin status
with create_session() as session:
    admin_service = AdminPhoneService(session)
    is_admin = admin_service.is_admin_phone("whatsapp:+5511999999999", tenant_id)
    print(f"Is admin: {is_admin}")
    
    # List admin phones
    phones = admin_service.list_admin_phones(tenant_id)
    print(f"Admin phones: {phones}")
```

### Issue 2: Flow Modifications Not Working

**Symptoms:** Bot confirms modification but flow doesn't change

**Possible causes:**
1. FlowChatService/FlowChatAgent not working properly
2. Flow not being persisted to database
3. LLM not generating valid modifications

**Debugging:**
```python
# Test FlowChatService directly
from app.services.flow_chat_service import FlowChatService
from app.agents.flow_chat_agent import FlowChatAgent
from app.core.llm import create_llm_client

llm = create_llm_client()
agent = FlowChatAgent(llm=llm)

with create_session() as session:
    service = FlowChatService(session, agent=agent)
    response = await service.send_user_message(
        flow_id,
        "Change the greeting to be more friendly"
    )
    print(f"Modified: {response.flow_was_modified}")
    print(f"Summary: {response.modification_summary}")
```

### Issue 3: Communication Style Not Taking Effect

**Symptoms:** Style updates confirmed but bot still communicates the same way

**Possible causes:**
1. Style is appended but LLM not respecting it
2. Cache issues
3. Style instruction too vague

**Debugging:**
```python
# Check actual style stored
with create_session() as session:
    tenant = get_tenant_by_id(session, tenant_id)
    print(tenant.project_config.communication_style)

# Try more specific instruction
"Não use emojis nas mensagens. Seja direto e profissional. Evite exclamações."
```

## Architecture Overview

### Flow of Admin Command

```
User Message: "Ta muito emoji, da uma maneirada"
    ↓
FlowProcessor.process_flow()
    ↓
FlowProcessor._check_admin_status() → True
    ↓
EnhancedFlowResponder.respond()
    ├─ _add_admin_instructions() adds admin-specific prompt
    └─ _select_contextual_tools() includes admin actions
    ↓
LLM detects: Communication style change request
    ↓
LLM response: PerformAction(
    actions=["stay"],
    messages=[{"text": "Posso fazer essa alteração?"}]
)
    ↓
User: "Sim"
    ↓
LLM response: PerformAction(
    actions=["update_communication_style", "stay"],
    communication_style_instruction="Use menos emojis...",
    messages=[{"text": "Estilo atualizado!"}]
)
    ↓
ToolExecutionService._handle_external_action()
    ↓
CommunicationStyleExecutor.execute()
    ├─ Checks admin status (security)
    ├─ Gets current style
    ├─ Appends new instruction
    └─ Updates tenant.project_config.communication_style
    ↓
ActionResult returned with success=True
    ↓
Bot sends confirmation message
```

## Key Files

| File | Purpose |
|------|---------|
| `admin_flow_cli.py` | Interactive CLI for testing admin commands |
| `app/core/flow_processor.py` | Admin status checking, flow processing |
| `app/services/admin_phone_service.py` | Admin phone management |
| `app/flow_core/services/responder.py` | Admin instructions, tool selection |
| `app/flow_core/actions/communication_style.py` | Communication style executor |
| `app/flow_core/actions/flow_modification.py` | Flow modification executor |
| `app/flow_core/services/tool_executor.py` | Action routing and execution |

## Best Practices

1. **Always test admin commands with the CLI first** before production use
2. **Use specific instructions** for communication style (not vague like "improve")
3. **Test the confirmation flow** - ensure users can cancel
4. **Verify persistence** - check database after modifications
5. **Use separate admin phones** - don't mix admin and customer testing on same number
6. **Document style changes** - keep track of what modifications were made

## Future Improvements

Potential enhancements to consider:

1. **Admin Incognito Mode**: Allow admins to disable admin features temporarily
2. **Style History**: Track all communication style changes with timestamps
3. **Rollback Capability**: Undo recent flow or style modifications
4. **Preview Mode**: Show what changes will happen before confirming
5. **Multi-language Admin Commands**: Support English and Portuguese equally well
6. **Admin Dashboard**: View and manage admin phones, style history, etc.

## Summary

The admin system is working and provides two powerful features:

1. ✅ **Communication Style Changes**: Admins can adjust bot tone, emoji usage, formality
2. ✅ **Flow Modifications**: Admins can modify flow structure during conversations

Both follow a **confirmation pattern** for safety, and both are **phone-based** (no PIN required).

To test: Use `admin_flow_cli.py` for interactive testing or test directly via WhatsApp CLI.

For your specific example ("Ta muito emoji, da uma maneirada"):
- System will detect it as communication style change
- Ask for confirmation
- Update tenant's `communication_style` field
- Future messages will use less emojis


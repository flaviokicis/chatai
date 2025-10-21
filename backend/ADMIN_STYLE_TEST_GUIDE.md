# Admin Communication Style Change - Manual Test Guide

## Quick Test (5 minutes)

### Setup

1. Start the WhatsApp CLI:
```bash
cd backend
make whatsapp-cli
```

2. The CLI will show you're connected as user `+19995551234`

### Test Steps

**STEP 1: Check if you're admin**

The default user `+19995551234` is NOT an admin. To test as admin, you need to:

Option A: Add yourself as admin in the database:
```bash
# In another terminal
cd backend
source .venv/bin/activate
python -c "
from app.db.session import create_session
from app.db.repository import get_tenant_by_id, update_tenant_admin_phones
from uuid import UUID

tenant_id = UUID('068b37cd-c090-710d-b0b6-5ca37c2887ff')
with create_session() as session:
    tenant = get_tenant_by_id(session, tenant_id)
    current_admins = tenant.admin_phone_numbers or []
    if '+19995551234' not in current_admins:
        update_tenant_admin_phones(session, tenant_id, current_admins + ['+19995551234'])
        session.commit()
        print('✅ Added +19995551234 as admin')
    else:
        print('✅ Already admin')
"
```

Option B: Run CLI with an admin phone:
```bash
# Edit the Makefile or run directly:
. .venv/bin/activate && uv run python -m app.flow_core.whatsapp_cli --phone +15550489424 --user-phone +5511999999999
```

**STEP 2: Start conversation**

```
You: Oi!
```

Bot should respond with the initial flow message.

**STEP 3: Request communication style change (in Portuguese)**

```
You: Ta muito formal, fala de forma mais calorosa e amigável
```

**Expected behavior:**
- Bot should **detect this as an admin command**
- Bot should **ask for confirmation**: "Entendi! Vou ajustar o estilo... Posso fazer essa alteração?"

**STEP 4: Confirm the change**

```
You: Sim, pode fazer
```

**Expected behavior:**
- Bot should **execute the UpdateCommunicationStyle tool**
- Bot should confirm: "Pronto! Ajustei o estilo..."
- Communication style should be **updated in database**

**STEP 5: Verify new style takes effect**

```
You: Qual o próximo passo?
```

**Expected behavior:**
- Bot should respond using the **new, warmer style**
- Response should feel more "calorosa e amigável"

### Verification

Check the database to see the updated style:

```bash
python -c "
from app.db.session import create_session
from app.db.repository import get_tenant_by_id
from uuid import UUID

with create_session() as session:
    tenant = get_tenant_by_id(session, UUID('068b37cd-c090-710d-b0b6-5ca37c2887ff'))
    if tenant and tenant.project_config:
        print('Communication Style:')
        print(tenant.project_config.communication_style)
"
```

## What to Look For

✅ **SUCCESS indicators:**
1. Bot detects "Ta muito formal..." as an admin command
2. Bot uses `PerformAction` tool to ask for confirmation
3. After "Sim", bot uses `UpdateCommunicationStyle` tool
4. Database shows the COMPLETE new style (not just appended)
5. Next messages use the new warmer tone

❌ **FAILURE indicators:**
1. Bot treats the request as a regular user answer
2. Bot doesn't ask for confirmation
3. Style is appended instead of replaced
4. New style doesn't take effect immediately

## Expected Tool Sequence

1. **Request:** "Ta muito formal..."
   - Tool: `PerformAction(actions=["stay"], messages=[...])`
   - Asks for confirmation

2. **Confirm:** "Sim, pode fazer"
   - Tool: `UpdateCommunicationStyle(updated_communication_style="...", messages=[...])`
   - Updates database with COMPLETE new style

3. **Next message:** Uses new style from database

## Implementation Notes

- The **confirmation message** will still use the old style (that's expected - it was generated before the change)
- **All messages AFTER** the confirmation should use the new style
- The style is **completely replaced**, not appended
- GPT-5 receives the **current style** in the prompt with label: "CURRENT COMMUNICATION STYLE (for admins to modify)"
- GPT-5 generates the **complete new style** by taking the current one and applying changes


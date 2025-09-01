# 🔧 Live Flow Editing System

## Overview

The Live Flow Editing System allows tenant administrators to modify conversation flows **during live conversations** without requiring PIN codes or special mode activation. This system replaces the old PIN-based testing mode with a seamless, phone-number-based admin system.

## Key Features

### ✅ **Seamless Integration**
- No PIN codes or mode activation required
- Works during normal WhatsApp conversations
- Admin users get special tools automatically
- Non-admin users see no difference

### ✅ **Admin Phone Management**
- Phone numbers stored in `Tenant.admin_phone_numbers` JSONB field
- Supports both `+5511999999999` and `whatsapp:+5511999999999` formats
- Multiple admin phones per tenant
- Database-driven, no API endpoints needed

### ✅ **Live Flow Modification**
- Uses existing chat-to-flow LLM system
- Stores tenant observations in node metadata
- Automatic flow versioning and persistence
- Conversation restart capability

## How It Works

### Phase 1: Flow Building from Scratch

When starting with an empty flow:

```
User: Ola!
AI: O fluxo está vazio. Vamos começar a construir juntos!

User: A primeira parte pode ser "Ola! Somos a barbearia Mestres da Tesoura!"
AI: Perfeito! E quando o usuário responder isso, o que devo fazer?

User: Se responder "quero marcar consulta", pergunta que horas
AI: Ótimo! E depois que ele informar o horário?

User: Aí fala "Ok, marcado!"
AI: Excelente! E se o usuário não quiser marcar consulta? Que outras situações podem acontecer?
```

The AI helps build the flow conversationally, asking follow-up questions and suggesting branches.

### Phase 2: Live Flow Editing

During normal conversations with existing flows:

```
Normal User: Preciso cortar meu cabelo!
AI: Ola! Qual corte você gostaria?

Admin User: Não responda assim, responda "Ola! Já tem horário marcado?"
AI: Ah, ok, anotado. Da próxima vez irei perguntar se já tem horário marcado!

Admin User: Vamos recomeçar pra testar
AI: Ok, vamos começar de novo. Oi!

Normal User: Oi
AI: Ola! Já tem horário marcado? (← Modified behavior)
```

## Technical Architecture

### Database Schema

```sql
-- Admin phone numbers stored in tenant
ALTER TABLE tenants ADD COLUMN admin_phone_numbers JSONB;

-- Example data
UPDATE tenants SET admin_phone_numbers = '["+5511999887766", "+5511888777666"]'::jsonb WHERE id = 'tenant-uuid';

-- Removed old training mode fields
-- ALTER TABLE flows DROP COLUMN training_password;
-- ALTER TABLE chat_threads DROP COLUMN training_mode;
-- ALTER TABLE chat_threads DROP COLUMN training_mode_since; 
-- ALTER TABLE chat_threads DROP COLUMN training_flow_id;
```

### Flow Processing Integration

```python
# In FlowProcessor._execute_flow()
is_admin = self._check_admin_status(request)
if is_admin:
    from app.flow_core.tool_schemas import ModifyFlowLive
    extra_tools.append(ModifyFlowLive)
    instruction_prefix = "ADMIN MODE: You have access to live flow modification..."

# Admin status checking
def _check_admin_status(self, request: FlowRequest) -> bool:
    user_phone = request.user_id  # e.g., "whatsapp:+5511999999999"
    tenant_id = request.project_context.tenant_id
    
    with create_session() as session:
        admin_service = AdminPhoneService(session)
        return admin_service.is_admin_phone(user_phone, tenant_id)
```

### Live Modification Tool

```python
class ModifyFlowLive(FlowResponse):
    """Modify the current flow based on admin instructions during conversation."""
    
    instruction: str = Field(
        description="The specific instruction about how to modify the flow behavior"
    )
    reason: Literal["admin_instruction"] = Field(
        default="admin_instruction",
        description="Reason for the modification",
    )
```

### Node Metadata Storage

Tenant observations are stored in node metadata:

```json
{
  "id": "greeting_node",
  "kind": "Question", 
  "prompt": "Ola! Já tem horário marcado?",
  "key": "initial_response",
  "metadata": {
    "tenant_observations": [
      "Admin requested: 'Não responda assim, responda Ola! Já tem horário marcado?'",
      "Changed greeting behavior on 2025-08-31"
    ]
  }
}
```

## System Components

### Core Files

1. **`AdminPhoneService`** (`app/services/admin_phone_service.py`)
   - Manages admin phone numbers
   - Checks admin status during conversations
   - Handles phone normalization (removes `whatsapp:` prefix)

2. **`ModifyFlowLive` Tool** (`app/flow_core/tool_schemas.py`)
   - Available only to admin users
   - Triggers live flow modification
   - Stores tenant instructions

3. **Live Modification Handler** (`app/flow_core/live_flow_modification_tool.py`)
   - Uses existing chat-to-flow LLM system
   - Enhances instructions with metadata storage
   - Returns user-friendly responses

4. **Flow Processor Integration** (`app/core/flow_processor.py`)
   - Checks admin status per request
   - Conditionally provides admin tools
   - Handles tool event responses

### Database Models

1. **`Tenant.admin_phone_numbers`** - JSONB array of admin phone numbers
2. **Node metadata** - Stores tenant observations and feedback
3. **Flow versioning** - Automatic versioning when flows are modified

## Usage Examples

### Setting Up Admin Phones

```sql
-- Add admin phone numbers to tenant
UPDATE tenants 
SET admin_phone_numbers = '["+5511999887766", "+5511888777666"]'::jsonb 
WHERE id = 'your-tenant-uuid';

-- Check current admin phones
SELECT admin_phone_numbers FROM tenants WHERE id = 'your-tenant-uuid';
```

### Testing Admin Status

```python
from app.services.admin_phone_service import AdminPhoneService
from app.db.session import create_session

with create_session() as session:
    admin_service = AdminPhoneService(session)
    
    # Check if phone is admin
    is_admin = admin_service.is_admin_phone("+5511999887766", tenant_id)
    print(f"Is admin: {is_admin}")
    
    # List all admin phones
    admin_phones = admin_service.list_admin_phones(tenant_id)
    print(f"Admin phones: {admin_phones}")
```

### Flow Building Conversation

The AI is enhanced to be genuinely helpful during flow building:

```python
# Enhanced prompt includes:
"## Flow Building Guidance:"
"When building flows from scratch, be genuinely helpful and curious:"
"- Ask follow-up questions to understand the complete user journey"
"- Suggest additional scenarios and edge cases"
"- Help create depth-first paths (complete one path before branching)"
"- Offer to create alternative branches after main paths are established"
"- Store tenant feedback in node metadata for future reference"
```

## Testing

### Integration Tests

Run the comprehensive test suite:

```bash
# Core functionality tests
python -m pytest tests/test_live_flow_editing_simple.py -v

# Full integration tests (requires LLM setup)
python -m pytest tests/test_live_flow_editing_integration.py -v
```

### Manual Testing

1. **Set up admin phone**:
   ```sql
   UPDATE tenants SET admin_phone_numbers = '["+5511999887766"]'::jsonb WHERE id = 'your-tenant-id';
   ```

2. **Test normal user** (should not see admin tools):
   ```
   POST /webhooks/twilio/whatsapp
   From: whatsapp:+5511888999777
   Body: "Hello"
   ```

3. **Test admin user** (should get ModifyFlowLive tool):
   ```
   POST /webhooks/twilio/whatsapp  
   From: whatsapp:+5511999887766
   Body: "Change the greeting to be more friendly"
   ```

## Migration from Old System

### What Was Removed

1. **PIN-based testing mode**
   - `EnterTrainingMode` tool
   - `TrainingModeService`
   - `WhatsAppTrainingHandler`
   - Password validation logic
   - Training mode database fields

2. **Database fields removed**:
   - `flows.training_password`
   - `chat_threads.training_mode`
   - `chat_threads.training_mode_since`
   - `chat_threads.training_flow_id`

### What Was Added

1. **Admin phone system**
   - `tenants.admin_phone_numbers` JSONB field
   - `AdminPhoneService` for management
   - Phone-based admin checking

2. **Live modification system**
   - `ModifyFlowLive` tool schema
   - Live modification handler
   - Node metadata storage
   - Enhanced flow building prompts

### Migration Steps

1. ✅ **Database migration applied** - Old fields removed, new field added
2. ✅ **Code cleanup completed** - All training mode references removed  
3. ✅ **New system implemented** - Admin phone checking and live modification working
4. ✅ **Tests passing** - Core functionality verified

## Benefits

### For Tenants
- **No PIN management** - Just use their phone number
- **Live editing** - Modify flows during real conversations
- **Natural interaction** - AI helps build flows conversationally
- **Immediate testing** - Can restart and test changes instantly

### For Development
- **Simpler architecture** - No complex mode switching
- **Better separation of concerns** - Admin checking isolated
- **Reuses existing systems** - Leverages chat-to-flow LLM
- **Maintainable code** - Clean, focused components

### For Users
- **Seamless experience** - No difference for normal users
- **Better flows** - Admins can refine based on real usage
- **Faster iterations** - No need to go to separate interface

## Conclusion

The Live Flow Editing System successfully replaces the complex PIN-based testing mode with a simple, powerful, and user-friendly system. Tenants can now build and refine their conversation flows naturally during real interactions, leading to better customer experiences and more efficient flow development.

🎉 **The system is production-ready and fully tested!**

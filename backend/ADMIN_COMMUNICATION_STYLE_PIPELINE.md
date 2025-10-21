# Admin Communication Style Update - Simple Pipeline

## Overview

Communication style updates are **COMPLETELY SEPARATE** from flow modifications. They are much simpler and don't touch the flow graph at all.

## What is Communication Style?

Communication style controls **HOW the bot talks**, not WHAT it asks:
- Tone (formal, casual, warm, direct)
- Emoji usage
- Message length (concise vs detailed)
- Personality traits

## What is NOT Communication Style?

These are **flow modifications** (different system):
- Changing questions
- Adding/removing steps
- Modifying flow logic
- Changing routing conditions

## Examples

### Communication Style Updates ✅
```
"Be more polite"
"Use more emojis"
"Fale de forma mais direta"
"Seja mais caloroso"
"Da uma maneirada nos emojis"
"Fale mais como uma pessoa, menos robótico"
"Use menos palavras, seja mais conciso"
```

### Flow Modifications ❌ (Wrong category)
```
"Change the greeting to ask for name first"  ← FLOW MODIFICATION
"Add a question about phone number"  ← FLOW MODIFICATION
"Remove the address question"  ← FLOW MODIFICATION
"Split this into two questions"  ← FLOW MODIFICATION
```

## Complete Pipeline (Communication Style Only)

```
┌─────────────────────────────────────────────────────────────────┐
│ 1️⃣  USER INPUT                                                  │
├─────────────────────────────────────────────────────────────────┤
│ Admin via WhatsApp:                                             │
│ "Be more polite and use more emojis"                            │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2️⃣  LLM RESPONDER                                               │
├─────────────────────────────────────────────────────────────────┤
│ • Detects admin status                                          │
│ • Adds admin instructions to prompt                             │
│ • Provides CURRENT communication style to LLM                   │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3️⃣  LLM ANALYZES REQUEST                                        │
├─────────────────────────────────────────────────────────────────┤
│ Current style: "Tom casual e direto"                            │
│                                                                  │
│ User request: "Be more polite and use more emojis"             │
│                                                                  │
│ LLM determines:                                                 │
│ ✓ This is a COMMUNICATION STYLE change                          │
│ ✓ NOT a flow structure change                                   │
│ ✓ Should use: update_communication_style action                 │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4️⃣  LLM RETURNS TOOL CALL                                       │
├─────────────────────────────────────────────────────────────────┤
│ Tool: PerformAction                                             │
│ {                                                                │
│   "actions": ["update_communication_style", "stay"],            │
│   "updated_communication_style": "Tom caloroso e educado.       │
│                                   Use emojis em saudações,      │
│                                   confirmações e despedidas.",  │
│   "messages": [{                                                 │
│     "text": "Vou ajustar para ser mais educado e usar emojis"  │
│   }]                                                             │
│ }                                                                │
│                                                                  │
│ NOTE: LLM generates COMPLETE new style, not just changes!       │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5️⃣  TOOL EXECUTION SERVICE                                      │
├─────────────────────────────────────────────────────────────────┤
│ Processes PerformAction tool                                    │
│                                                                  │
│ For action "update_communication_style":                        │
│   → Calls _handle_external_action()                             │
│   → Gets CommunicationStyleExecutor from ActionRegistry         │
│   → Passes updated_communication_style to executor              │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6️⃣  COMMUNICATION STYLE EXECUTOR                                │
│    (actions/communication_style.py)                             │
├─────────────────────────────────────────────────────────────────┤
│ async def execute(parameters, context):                         │
│                                                                  │
│   1. Extract new_style from parameters                          │
│   2. Verify user is admin:                                      │
│      - Check phone in tenant.admin_phone_numbers                │
│      - If not admin → Return error                              │
│                                                                  │
│   3. Update database directly:                                  │
│      - Call update_tenant_project_config()                      │
│      - Set communication_style = new_style                      │
│      - REPLACES old style entirely (not append)                 │
│                                                                  │
│   4. Commit transaction                                         │
│                                                                  │
│   5. Return ActionResult                                        │
│                                                                  │
│ NO FlowChatAgent involved!                                      │
│ NO FlowModificationService involved!                            │
│ NO flow graph changes!                                          │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7️⃣  DATABASE UPDATED                                            │
├─────────────────────────────────────────────────────────────────┤
│ Table: tenants                                                  │
│ Field: project_config.communication_style                       │
│                                                                  │
│ Old value:                                                       │
│   "Tom casual e direto"                                         │
│                                                                  │
│ New value:                                                       │
│   "Tom caloroso e educado. Use emojis em saudações,            │
│    confirmações e despedidas."                                  │
│                                                                  │
│ ✅ COMMITTED                                                     │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 8️⃣  RETURNS ACTION RESULT                                       │
├─────────────────────────────────────────────────────────────────┤
│ CommunicationStyleExecutor returns:                             │
│                                                                  │
│ ActionResult(                                                   │
│   success=True,                                                 │
│   message="✅ Estilo de comunicação atualizado com sucesso!    │
│            As próximas mensagens seguirão o novo estilo.",      │
│   data={                                                         │
│     "new_style": "Tom caloroso e educado...",                   │
│     "tenant_id": "..."                                          │
│   }                                                              │
│ )                                                                │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 9️⃣  FEEDBACK LOOP                                               │
├─────────────────────────────────────────────────────────────────┤
│ Runner detects external action result                           │
│                                                                  │
│ Builds feedback prompt:                                         │
│ ┌─────────────────────────────────────────────────┐             │
│ │ === EXTERNAL ACTION EXECUTION RESULT ===        │             │
│ │ Action: update_communication_style              │             │
│ │ Status: SUCCESS                                 │             │
│ │ Result: ✅ Estilo atualizado com sucesso        │             │
│ │                                                 │             │
│ │ Generate truthful response based on result.    │             │
│ └─────────────────────────────────────────────────┘             │
│                                                                  │
│ Makes second LLM call for truthful response                     │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 🔟  LLM GENERATES RESPONSE                                      │
├─────────────────────────────────────────────────────────────────┤
│ {                                                                │
│   "messages": [{                                                 │
│     "text": "✅ Pronto! Agora vou ser mais educado e usar      │
│              emojis nas mensagens 😊"                            │
│   }]                                                             │
│ }                                                                │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1️⃣1️⃣  USER RECEIVES MESSAGE                                     │
├─────────────────────────────────────────────────────────────────┤
│ WhatsApp message:                                               │
│ "✅ Pronto! Agora vou ser mais educado e usar emojis 😊"        │
│                                                                  │
│ Next message from bot will use new style!                       │
└─────────────────────────────────────────────────────────────────┘
```

## Key Differences from Flow Modification

| Aspect | Communication Style | Flow Modification |
|--------|---------------------|-------------------|
| **What it changes** | HOW bot talks (tone, style) | WHAT bot asks (questions, structure) |
| **Database table** | `tenant.project_config` | `flows.definition` |
| **Executor** | `CommunicationStyleExecutor` | `FlowModificationExecutor` |
| **Uses FlowChatAgent** | ❌ No | ✅ Yes |
| **Uses FlowModificationService** | ❌ No | ✅ Yes |
| **Complexity** | Simple DB update | Complex graph modification |
| **LLM calls** | 2 (decision + feedback) | 3+ (decision + flow editing + feedback) |
| **Atomic operations** | Single field update | Batch actions on graph |
| **Versioning** | No versioning | Full version history |
| **Examples** | "Be more polite" | "Change greeting question" |

## How LLM Decides Which Action to Use

The LLM is taught to distinguish based on these patterns:

### Communication Style Triggers
```
TONE/STYLE keywords:
- "Seja mais [formal/informal/técnico/simples/direto/caloroso]"
- "Fale mais/menos [assim/desse jeito]"
- "Use/Não use emojis"
- "Seja mais [educado/direto/conciso/detalhado]"
- "Fale mais como [humano/pessoa/amigo]"
- "Evite dizer X" / "Use Y ao invés de X"

NO structural mentions - just HOW to communicate
```

### Flow Modification Triggers
```
STRUCTURAL keywords:
- "Change this question to..."
- "Add/remove a question about..."
- "Split this into multiple questions"
- "Don't ask about X anymore"
- "Make the greeting say Y"
- "Break this node into N steps"

Mentions specific nodes, questions, or flow structure
```

## Code Flow Comparison

### Communication Style (Simple)
```python
PerformAction(action="update_communication_style")
  ↓
ToolExecutionService._handle_external_action()
  ↓
CommunicationStyleExecutor.execute()
  ↓
update_tenant_project_config(communication_style=new_style)
  ↓
Database.commit()
  ↓
Return ActionResult
```

### Flow Modification (Complex)
```python
PerformAction(action="modify_flow")
  ↓
ToolExecutionService._handle_external_action()
  ↓
FlowModificationExecutor.execute()
  ↓
FlowChatService.send_user_message()
  ↓
FlowChatAgent.process()  ← Separate LLM call!
  ↓
LLM returns BatchFlowActionsRequest
  ↓
FlowModificationService.execute_batch_actions()
  ↓
Loop: add_node, update_node, delete_node, etc.
  ↓
Validate flow
  ↓
update_flow_with_versioning()
  ↓
Database.commit()
  ↓
Return ActionResult
```

## Input/Output

### Input (from LLM's PerformAction)
```python
{
    "actions": ["update_communication_style", "stay"],
    "updated_communication_style": "Tom caloroso e educado. Use emojis.",
    "messages": [{"text": "Vou ajustar o estilo..."}]
}
```

### Processing
```python
# CommunicationStyleExecutor
parameters = {
    "updated_communication_style": "Tom caloroso e educado. Use emojis."
}

context = {
    "user_id": "whatsapp:+5511999999999",
    "tenant_id": UUID("..."),
    "session_id": "...",
    "channel_id": "whatsapp"
}

# Verify admin
is_admin = admin_service.is_admin_phone(user_id, tenant_id)
if not is_admin:
    return ActionResult(success=False, message="Only admins...")

# Update database
update_tenant_project_config(
    tenant_id=tenant_id,
    communication_style="Tom caloroso e educado. Use emojis."
)
```

### Output
```python
ActionResult(
    success=True,
    message="✅ Estilo de comunicação atualizado com sucesso! As próximas mensagens seguirão o novo estilo.",
    data={
        "new_style": "Tom caloroso e educado. Use emojis.",
        "tenant_id": "..."
    }
)
```

## Important Implementation Details

### 1. Complete Replacement, Not Append
```python
# OLD (wrong): Appending
old_style = "Tom casual"
new_instruction = "Use emojis"
result = f"{old_style}. {new_instruction}"  # "Tom casual. Use emojis"

# NEW (correct): Complete replacement
old_style = "Tom casual"
new_instruction = "Use emojis"
# LLM receives old style, generates complete new one:
result = "Tom casual. Use emojis em saudações."  # Complete replacement
```

### 2. Minimal Changes
LLM is instructed to:
- Take current style as base
- Apply ONLY requested changes
- Be REACTIVE not PROACTIVE
- Don't add extra instructions

Example:
```
Current: "Tom casual e direto"
Request: "Use more emojis"
Output: "Tom casual e direto. Use emojis em saudações." ✅

NOT: "Tom casual, direto, amigável, acolhedor. Use muitos emojis, 
      seja caloroso, use linguagem informal..." ❌ (too much!)
```

### 3. Admin Verification
```python
# Always verify admin status
admin_service = AdminPhoneService(session)
is_admin = admin_service.is_admin_phone(
    phone_number=user_id,  # e.g., "whatsapp:+5511999999999"
    tenant_id=tenant_id
)

if not is_admin:
    return ActionResult(
        success=False,
        message="Apenas administradores podem alterar o estilo."
    )
```

### 4. Immediate Effect
```python
# After commit, next message uses new style immediately
session.commit()

# Next LLM call for this tenant will include:
# "Communication Style: Tom caloroso e educado. Use emojis."
```

## Error Handling

| Error | Response |
|-------|----------|
| Missing `updated_communication_style` | "Erro: Novo estilo não fornecido" |
| User not admin | "Apenas administradores podem alterar" |
| Tenant not found | "Erro: Inquilino não encontrado" |
| Database error | "Erro inesperado ao atualizar" |

All errors are logged and return `ActionResult(success=False)` with user-friendly Portuguese messages.

## Testing

### Manual Test via WhatsApp CLI
```bash
cd backend
python admin_flow_cli.py
```

Then send:
```
Admin: "Seja mais caloroso e use emojis"
```

### Automated Test
```bash
cd backend
python tests/integration/whatsapp_cli_admin_tester.py
```

Round 2 tests communication style update.

## Summary

**Communication Style = Simple Database Update**
- No flow graph involved
- No FlowChatAgent
- No batch actions
- Just: LLM → CommunicationStyleExecutor → Database
- Updates single field in tenant config
- Takes effect immediately

**Flow Modification = Complex Graph Surgery**
- Modifies flow structure
- Uses FlowChatAgent
- Batch atomic actions
- Multiple validations
- Version history
- See separate ADMIN_EDIT_FLOW_PIPELINE.md



# Admin Systems: Flow Modification vs Communication Style

## Quick Reference

| Question | Flow Modification | Communication Style |
|----------|-------------------|---------------------|
| **What does it change?** | Flow graph structure (nodes, edges, questions) | How the bot talks (tone, style, formality) |
| **Example request** | "Change greeting to ask for name" | "Be more polite" |
| **LLM action** | `modify_flow` | `update_communication_style` |
| **Executor** | `FlowModificationExecutor` | `CommunicationStyleExecutor` |
| **Uses FlowChatAgent?** | ✅ Yes (separate LLM agent) | ❌ No |
| **Uses FlowModificationService?** | ✅ Yes | ❌ No |
| **Database table** | `flows.definition` | `tenant.project_config.communication_style` |
| **Complexity** | High (graph surgery) | Low (simple update) |
| **LLM calls** | 3+ | 2 |
| **Versioning** | ✅ Full history | ❌ Simple replacement |
| **Atomic operations** | ✅ Batch actions | ❌ Single field |

## Flow Modification (Structural Changes)

### What it changes:
- Questions asked
- Flow structure (nodes, edges)
- Routing logic
- Data collection steps
- Question order

### Examples:
```
✅ "Change the greeting to ask for their name"
✅ "Add a question about phone number"
✅ "Split this into two separate questions"
✅ "Remove the address question"
✅ "Make the bot ask about preferences first"
✅ "Change this prompt to say X instead of Y"
```

### Pipeline:
```
User Request
  ↓
LLM Decision (PerformAction with modify_flow)
  ↓
FlowModificationExecutor
  ↓
FlowChatService
  ↓
FlowChatAgent (SEPARATE LLM CALL)
  ↓
BatchFlowActionsRequest (add_node, update_node, etc.)
  ↓
FlowModificationService (atomic execution)
  ↓
Database: flows.definition updated
  ↓
Feedback Loop (truthful response)
  ↓
User sees result
```

### Complexity: HIGH
- Involves graph manipulation
- Requires validation
- Atomic batch operations
- Version control
- Multiple LLM calls

## Communication Style (Tone/Manner Changes)

### What it changes:
- Tone (formal, casual, warm, direct)
- Emoji usage
- Message length
- Personality traits
- Word choices

### Examples:
```
✅ "Be more polite"
✅ "Use more emojis"
✅ "Fale de forma mais direta"
✅ "Seja mais caloroso"
✅ "Use menos palavras"
✅ "Fale mais como uma pessoa"
✅ "Da uma maneirada nos emojis"
```

### Pipeline:
```
User Request
  ↓
LLM Decision (PerformAction with update_communication_style)
  ↓
CommunicationStyleExecutor
  ↓
Verify admin status
  ↓
Database: tenant.project_config.communication_style updated
  ↓
Feedback Loop (truthful response)
  ↓
User sees result
```

### Complexity: LOW
- Simple database update
- No graph manipulation
- Single field replacement
- No version control needed
- Only 2 LLM calls

## How LLM Decides Which to Use

### Flow Modification Keywords:
- "Change [this question/prompt] to..."
- "Add/remove a question about..."
- "Split this node/question into..."
- "Make the greeting say..."
- "Ask about X before Y"
- Any mention of nodes, steps, structure

### Communication Style Keywords:
- "Be more [polite/formal/casual/direct/warm]"
- "Use [more/less/no] emojis"
- "Speak more like [a person/a friend]"
- "Make messages [shorter/longer]"
- "Change the tone to..."
- "Fale mais/menos [assim/desse jeito]"
- No mention of questions or structure

## Code Comparison

### Flow Modification
```python
# actions/flow_modification.py
class FlowModificationExecutor(ActionExecutor):
    async def execute(self, parameters, context):
        instruction = parameters["flow_modification_instruction"]
        flow_id = parameters["flow_id"]
        
        # Create specialized agent
        agent = FlowChatAgent(llm=self._llm_client)
        service = FlowChatService(session, agent=agent)
        
        # Agent makes ANOTHER LLM call
        response = await service.send_user_message(flow_id, instruction)
        
        # Agent returns batch actions:
        # [
        #   {"action": "update_node", "node_id": "...", "updates": {...}},
        #   {"action": "add_edge", "source": "...", "target": "..."}
        # ]
        
        # FlowModificationService executes atomically
        # Database flows.definition updated
        
        return ActionResult(success=True, ...)
```

### Communication Style
```python
# actions/communication_style.py
class CommunicationStyleExecutor(ActionExecutor):
    async def execute(self, parameters, context):
        new_style = parameters["updated_communication_style"]
        
        # Verify admin
        is_admin = admin_service.is_admin_phone(user_id, tenant_id)
        if not is_admin:
            return ActionResult(success=False, message="Only admins...")
        
        # Simple database update
        update_tenant_project_config(
            tenant_id=tenant_id,
            communication_style=new_style  # REPLACES old style
        )
        
        session.commit()
        
        return ActionResult(success=True, ...)
```

## When to Use Which

### Use Flow Modification when:
- Changing what questions are asked
- Modifying flow structure
- Adding/removing steps
- Changing routing logic
- Altering data collection

### Use Communication Style when:
- Changing tone or personality
- Adjusting emoji usage
- Modifying formality level
- Changing message style
- Adjusting verbosity

## Common Mistakes

### ❌ Wrong: Using flow modification for style
```
Admin: "Be more polite"
System: ❌ Calls FlowModificationExecutor
Result: ❌ Tries to modify flow graph unnecessarily
```

### ✅ Correct: Using communication style
```
Admin: "Be more polite"
System: ✅ Calls CommunicationStyleExecutor
Result: ✅ Updates tenant.communication_style field
```

### ❌ Wrong: Using communication style for structure
```
Admin: "Change the greeting to ask for name"
System: ❌ Calls CommunicationStyleExecutor
Result: ❌ No structural change, just style update
```

### ✅ Correct: Using flow modification
```
Admin: "Change the greeting to ask for name"
System: ✅ Calls FlowModificationExecutor
Result: ✅ Updates flow graph structure
```

## Database Impact

### Flow Modification
```sql
-- Updates flow definition
UPDATE flows
SET definition = '{"nodes": [...], "edges": [...]}',
    updated_at = NOW()
WHERE id = 'flow-uuid';

-- Creates version
INSERT INTO flow_versions (flow_id, version, definition, change_description)
VALUES ('flow-uuid', 5, '...', 'Updated greeting node');
```

### Communication Style
```sql
-- Updates tenant config
UPDATE tenants
SET project_config = jsonb_set(
    project_config,
    '{communication_style}',
    '"Tom caloroso e educado. Use emojis."'
)
WHERE id = 'tenant-uuid';
```

## Performance Comparison

| Metric | Flow Modification | Communication Style |
|--------|-------------------|---------------------|
| LLM calls | 3+ | 2 |
| Database writes | 2+ (flow + version) | 1 (tenant config) |
| Validation steps | Multiple | Simple admin check |
| Average latency | ~3-5 seconds | ~1-2 seconds |
| Complexity | O(n) graph operations | O(1) field update |

## Testing

### Flow Modification
```bash
cd backend
python admin_flow_cli.py --flow-file playground/flow_example.json

# Then:
Admin: "Change the greeting to ask for email first"
```

### Communication Style
```bash
cd backend
python tests/integration/whatsapp_cli_admin_tester.py

# Round 2 automatically tests:
Admin: "quero solicitar que as respostas passem a usar mais emojis"
```

## Summary

**Two completely separate systems with different purposes:**

1. **Flow Modification** = Structural surgery on the conversation flow
   - Complex, multi-step process
   - Involves specialized FlowChatAgent
   - Batch atomic operations
   - Full versioning

2. **Communication Style** = Simple tone adjustment
   - Straightforward database update
   - No specialized agent needed
   - Single field replacement
   - Immediate effect

**The LLM is trained to distinguish between them based on the request content.**


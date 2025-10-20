# Admin Edit Flow - Visual Pipeline Diagram

## ⚠️ IMPORTANT: Two Separate Systems

This diagram shows **FLOW MODIFICATION** only (structural changes to the graph).

**Communication Style updates** (tone, formality, emoji usage) are MUCH SIMPLER:
- No FlowChatAgent involved
- No FlowModificationService involved  
- Just: LLM → CommunicationStyleExecutor → Database update
- See: `ADMIN_COMMUNICATION_STYLE_PIPELINE.md`

**Examples to distinguish:**
- "Be more polite" → Communication Style (different pipeline)
- "Change greeting question" → Flow Modification (this pipeline)

## Flow Modification Pipeline Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ADMIN EDIT FLOW PIPELINE                            │
└─────────────────────────────────────────────────────────────────────────────┘

1️⃣  USER INPUT
    ┌──────────────────────────────────────┐
    │ Admin via WhatsApp:                  │
    │ "Change greeting to be professional" │
    └──────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 2️⃣  LLM RESPONDER (llm_responder.py)                                     │
├───────────────────────────────────────────────────────────────────────────┤
│ • Receives message + context                                              │
│ • Checks: is_admin = True                                                 │
│ • Adds admin instructions to prompt                                       │
│ • Calls EnhancedFlowResponder                                             │
└───────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 3️⃣  ENHANCED FLOW RESPONDER (services/responder.py)                      │
├───────────────────────────────────────────────────────────────────────────┤
│ LLM receives prompt with admin instructions                               │
│                                                                            │
│ Prompt includes:                                                           │
│ ✓ How to detect admin commands                                            │
│ ✓ Available actions: modify_flow, update_communication_style              │
│ ✓ Confirmation pattern requirements                                       │
│ ✓ Current flow state                                                       │
│                                                                            │
│ LLM decides: This is an admin command!                                    │
└───────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 4️⃣  LLM RETURNS TOOL CALL                                                │
├───────────────────────────────────────────────────────────────────────────┤
│ Tool: PerformAction                                                        │
│ {                                                                          │
│   "actions": ["modify_flow", "stay"],                                     │
│   "flow_modification_instruction": "Change greeting to professional",     │
│   "messages": [{                                                           │
│     "text": "I'll modify the greeting to be more professional..."         │
│   }]                                                                       │
│ }                                                                          │
└───────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 5️⃣  TOOL EXECUTION SERVICE (services/tool_executor.py)                   │
├───────────────────────────────────────────────────────────────────────────┤
│ Processes PerformAction                                                    │
│                                                                            │
│ For each action in ["modify_flow", "stay"]:                               │
│                                                                            │
│   ┌─────────────────────┬────────────────────────┐                        │
│   │ "stay"              │ "modify_flow"          │                        │
│   │ → Internal action   │ → External action      │                        │
│   │ → Execute now       │ → Needs execution!     │                        │
│   └─────────────────────┴────────────────────────┘                        │
│                                                                            │
│ Calls: _handle_external_action("modify_flow", ...)                        │
└───────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 6️⃣  ACTION REGISTRY → FLOW MODIFICATION EXECUTOR                         │
├───────────────────────────────────────────────────────────────────────────┤
│ • Gets FlowModificationExecutor from registry                             │
│ • Passes: instruction + flow_id + context                                 │
│ • Executor.execute() begins...                                            │
└───────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 7️⃣  FLOW MODIFICATION EXECUTOR (actions/flow_modification.py)            │
├───────────────────────────────────────────────────────────────────────────┤
│ Creates:                                                                   │
│   • FlowChatAgent (with LLM client)                                       │
│   • FlowChatService (with DB session)                                     │
│                                                                            │
│ Calls: service.send_user_message(flow_id, instruction)                   │
└───────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 8️⃣  FLOW CHAT SERVICE (services/flow_chat_service.py)                    │
├───────────────────────────────────────────────────────────────────────────┤
│ • Saves user message to flow_chat_messages table                          │
│ • Loads flow definition from database                                     │
│ • Loads conversation history                                              │
│ • Calls: agent.process(flow, history, flow_id)                           │
└───────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 9️⃣  FLOW CHAT AGENT (agents/flow_chat_agent.py)                          │
├───────────────────────────────────────────────────────────────────────────┤
│ Builds specialized prompt:                                                │
│ ┌─────────────────────────────────────────────────────────────┐           │
│ │ Flow Language Documentation:                                │           │
│ │ - Nodes: Question, Decision, Terminal, Action, Subflow     │           │
│ │ - Edges: source → target with guards                       │           │
│ │                                                             │           │
│ │ Available Actions:                                          │           │
│ │ - add_node, update_node, delete_node                       │           │
│ │ - add_edge, update_edge, delete_edge                       │           │
│ │ - set_entry                                                 │           │
│ │                                                             │           │
│ │ Current Flow:                                               │           │
│ │ {JSON representation of flow}                              │           │
│ │                                                             │           │
│ │ User instruction: "Change greeting to professional"        │           │
│ │                                                             │           │
│ │ Generate batch actions to fulfill this request.            │           │
│ └─────────────────────────────────────────────────────────────┘           │
│                                                                            │
│ Makes LLM call with tool: BatchFlowActionsRequest                         │
└───────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 🔟  LLM RETURNS BATCH ACTIONS                                             │
├───────────────────────────────────────────────────────────────────────────┤
│ {                                                                          │
│   "actions": [                                                             │
│     {                                                                      │
│       "action": "update_node",                                            │
│       "node_id": "greeting",                                              │
│       "updates": {                                                         │
│         "prompt": "Good afternoon. How may I assist you today?"           │
│       }                                                                    │
│     }                                                                      │
│   ]                                                                        │
│ }                                                                          │
└───────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 1️⃣1️⃣  FLOW MODIFICATION SERVICE (services/flow_modification_service.py)  │
├───────────────────────────────────────────────────────────────────────────┤
│ execute_batch_actions(flow, actions, flow_id)                             │
│                                                                            │
│ 1. Creates deep copy of flow (atomicity)                                  │
│                                                                            │
│ 2. For each action:                                                        │
│    ┌──────────────────────────────────────────┐                           │
│    │ Action: "update_node"                    │                           │
│    │ Node ID: "greeting"                      │                           │
│    │ Updates: { prompt: "Good afternoon..." } │                           │
│    ├──────────────────────────────────────────┤                           │
│    │ Execute: _update_node()                  │                           │
│    │ → Find node in flow.nodes[]              │                           │
│    │ → Apply updates                          │                           │
│    │ → Return ActionResult(success=True)      │                           │
│    └──────────────────────────────────────────┘                           │
│                                                                            │
│ 3. Validate modified flow                                                 │
│    ✓ FlowCompiler validates structure                                     │
│    ✓ Checks for errors                                                    │
│                                                                            │
│ 4. Persist to database                                                    │
│    → repository.update_flow_with_versioning()                             │
│    → Updates flows.definition                                             │
│    → Creates flow_versions entry                                          │
│    → Commits transaction                                                  │
└───────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 1️⃣2️⃣  DATABASE UPDATED ✅                                                 │
├───────────────────────────────────────────────────────────────────────────┤
│ flows table:                                                               │
│   - definition: {updated flow JSON}                                        │
│   - updated_at: 2025-10-20 15:30:00                                       │
│                                                                            │
│ flow_versions table:                                                       │
│   - version: 5                                                             │
│   - definition: {updated flow JSON}                                        │
│   - change_description: "Batch modification: ..."                         │
│   - created_by: "flow_chat_agent"                                         │
└───────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 1️⃣3️⃣  RETURNS UP THE STACK                                               │
├───────────────────────────────────────────────────────────────────────────┤
│ FlowModificationService                                                    │
│   → BatchActionResult(success=True, ...)                                  │
│       ▼                                                                    │
│ FlowChatAgent                                                              │
│   → FlowChatResponse(flow_was_modified=True, ...)                         │
│       ▼                                                                    │
│ FlowChatService                                                            │
│   → FlowChatServiceResponse(...)                                          │
│       ▼                                                                    │
│ FlowModificationExecutor                                                   │
│   → ActionResult(                                                          │
│       success=True,                                                        │
│       message="✅ Fluxo modificado com sucesso!",                          │
│       data={"summary": "Updated node 'greeting'"}                          │
│     )                                                                      │
│       ▼                                                                    │
│ ToolExecutionService                                                       │
│   → ToolExecutionResult(                                                   │
│       external_action_executed=True,                                       │
│       external_action_result=ActionResult(...)                             │
│     )                                                                      │
└───────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 1️⃣4️⃣  FEEDBACK LOOP (feedback/loop.py)                                   │
├───────────────────────────────────────────────────────────────────────────┤
│ Runner detects: tool_result.requires_llm_feedback = True                  │
│                                                                            │
│ Creates feedback prompt:                                                  │
│ ┌─────────────────────────────────────────────────────────────┐           │
│ │ === EXTERNAL ACTION EXECUTION RESULT ===                    │           │
│ │ Action: modify_flow                                         │           │
│ │ Status: SUCCESS                                             │           │
│ │ Result: ✅ Fluxo modificado com sucesso!                    │           │
│ │ Data: {"summary": "Updated node 'greeting'"}               │           │
│ │                                                             │           │
│ │ IMPORTANT: The action has ALREADY been executed.           │           │
│ │ Respond based on the ACTUAL result above.                  │           │
│ │                                                             │           │
│ │ Generate messages to inform the user.                      │           │
│ └─────────────────────────────────────────────────────────────┘           │
│                                                                            │
│ Makes SECOND LLM call                                                     │
└───────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 1️⃣5️⃣  LLM GENERATES TRUTHFUL RESPONSE                                    │
├───────────────────────────────────────────────────────────────────────────┤
│ Based on ACTUAL result (not speculation), LLM returns:                    │
│                                                                            │
│ {                                                                          │
│   "messages": [                                                            │
│     {                                                                      │
│       "text": "✅ Done! I changed the greeting to be more professional.", │
│       "delay_ms": 0                                                        │
│     },                                                                     │
│     {                                                                      │
│       "text": "New greeting: 'Good afternoon. How may I assist you?'",   │
│       "delay_ms": 1000                                                     │
│     }                                                                      │
│   ]                                                                        │
│ }                                                                          │
└───────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 1️⃣6️⃣  WHATSAPP ADAPTER SENDS MESSAGES                                    │
├───────────────────────────────────────────────────────────────────────────┤
│ Messages sent to user via WhatsApp:                                       │
│                                                                            │
│ ┌────────────────────────────────────────────────┐                        │
│ │ ✅ Done! I changed the greeting to be more     │                        │
│ │    professional.                                │                        │
│ └────────────────────────────────────────────────┘                        │
│          (1 second delay)                                                  │
│ ┌────────────────────────────────────────────────┐                        │
│ │ New greeting: 'Good afternoon. How may I       │                        │
│ │ assist you?'                                    │                        │
│ └────────────────────────────────────────────────┘                        │
│                                                                            │
│ ✅ COMPLETE!                                                               │
└───────────────────────────────────────────────────────────────────────────┘
```

## Key Architectural Decisions

### 🎯 **Why Separate Flow Modification from Main Flow?**

The admin edit system uses a **completely separate LLM agent** (`FlowChatAgent`) for flow modifications, not the main flow agent. This is because:

1. **Different Context**: Flow modification needs the entire flow structure, not just current node
2. **Different Tools**: Uses `BatchFlowActionsRequest`, not `PerformAction`
3. **Different Prompt**: Needs flow language documentation and editing instructions
4. **Isolation**: Editing errors don't affect user conversations

### 🔄 **Why Two LLM Calls?**

```
First LLM Call (EnhancedFlowResponder):
  Input: User request
  Output: What to do + intended messages
  Problem: Doesn't know if action will succeed!

External Action Execution:
  Actually performs the modification
  May succeed or fail

Second LLM Call (FeedbackLoop):
  Input: Actual action result
  Output: Truthful messages based on reality
  Benefit: Never lies to users!
```

### 🧱 **Why Batch Actions?**

Instead of asking LLM to generate JSON directly:
- LLM makes a single tool call
- Tool accepts array of actions
- Actions are validated and executed atomically
- If one fails, all rollback
- More reliable than free-form JSON editing

### 💾 **Why Immediate Persistence?**

- Changes are persisted **immediately** after validation
- Not deferred to end of conversation
- Admin can test changes right away
- Versioning allows rollback if needed

### 🛡️ **Why Atomicity?**

```python
working_flow = copy.deepcopy(flow)  # Work on copy

for action in actions:
    result = execute(action)
    if not result.success:
        return ROLLBACK_ALL  # Original flow unchanged

persist(working_flow)  # Only if all succeed
```

Benefits:
- All changes apply together or none apply
- No partial/broken states
- Database consistency guaranteed

## Data Structures at Each Layer

### Input to Pipeline
```python
{
    "user_message": "Change greeting to professional",
    "is_admin": True,
    "context": FlowContext(...),
    "project_context": ProjectContext(...)
}
```

### LLM Tool Call
```python
{
    "tool_calls": [{
        "name": "PerformAction",
        "arguments": {
            "actions": ["modify_flow", "stay"],
            "flow_modification_instruction": "...",
            "messages": [...]
        }
    }]
}
```

### Tool Execution Result
```python
ToolExecutionResult(
    external_action_executed=True,
    external_action_result=ActionResult(
        success=True,
        message="✅ Flow modified successfully",
        data={"summary": "Updated greeting"}
    ),
    metadata={"messages": [...]}
)
```

### Batch Actions
```python
[
    {
        "action": "update_node",
        "node_id": "greeting",
        "updates": {"prompt": "Good afternoon..."}
    }
]
```

### Database Update
```sql
UPDATE flows
SET definition = '{"nodes": [...], "edges": [...]}'
WHERE id = 'flow-uuid';

INSERT INTO flow_versions (flow_id, version, definition, change_description)
VALUES ('flow-uuid', 5, '...', 'Batch modification: ...');
```

### Final Response
```python
{
    "messages": [
        {"text": "✅ Done! ...", "delay_ms": 0},
        {"text": "New greeting: ...", "delay_ms": 1000}
    ]
}
```

## Error Handling at Each Layer

| Layer | Error Type | Handling |
|-------|-----------|----------|
| **LLM Responder** | LLM timeout | Retry with backoff |
| **Tool Executor** | Unknown action | Return error ActionResult |
| **Flow Mod Executor** | Missing flow_id | Return ActionResult(success=False) |
| **Flow Chat Agent** | Invalid JSON | Retry LLM call (max 2 retries) |
| **Flow Mod Service** | Action fails | Rollback all, return error |
| **Database** | Constraint violation | Rollback transaction |
| **Feedback Loop** | LLM timeout | Use fallback message |

## Performance Optimizations

1. **Action Registry Reuse**: Created once, reused across requests
2. **Database Sessions**: Scoped properly to avoid leaks
3. **Deep Copy Only When Needed**: For atomicity
4. **Validation Caching**: FlowCompiler caches results
5. **Parallel Actions**: Internal actions execute in sequence (for consistency)
6. **Connection Pooling**: SQLAlchemy handles DB connections efficiently

## Observability

Every layer logs:
- ✅ Success events
- ❌ Error events
- 📊 Metrics (timing, counts)
- 🔍 Debug info (in dev mode)

Example log flow:
```
🤖 FLOW CHAT AGENT: Starting processing
📨 FLOW CHAT SERVICE: Processing user message
🔧 FLOW MODIFICATION SERVICE: Executing batch actions
💾 FLOW PERSISTENCE: Saving to database
✅ FLOW PERSISTED SUCCESSFULLY
🔄 FEEDBACK LOOP: Processing modify_flow result
📤 Sending messages to user
```

## Testing Strategy

1. **Unit Tests**: Each service in isolation
2. **Integration Tests**: Full pipeline with test database
3. **E2E Tests**: WhatsApp simulation with real LLM
4. **Admin CLI**: Interactive testing tool for developers

Example CLI usage:
```bash
python admin_flow_cli.py --flow-file playground/flow_example.json
```

## Security Considerations

1. **Admin Verification**: Phone number must be in `tenant.admin_phone_numbers`
2. **SQL Injection**: Uses parameterized queries
3. **JSON Injection**: Validates all JSON structures
4. **Rate Limiting**: Can be added at API level
5. **Audit Trail**: All changes tracked in `flow_versions`
6. **Rollback Capability**: Can revert to any previous version


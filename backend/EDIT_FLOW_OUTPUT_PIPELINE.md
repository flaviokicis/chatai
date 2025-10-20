# Edit Flow LLM Output - Complete Pipeline

## What the Edit LLM Returns

The FlowChatAgent returns a `FlowChatResponse`:

```python
class FlowChatResponse(NamedTuple):
    messages: list[str]                    # Messages to show admin
    flow_was_modified: bool                # Whether flow was actually changed
    modification_summary: str | None = None  # Summary of what changed
```

## Complete Output Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│ 1. FlowChatAgent.process()                                  │
│    Input: flow, history, flow_id, session                   │
│    LLM Call: BatchFlowActionsRequest tool                   │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. LLM Returns Actions Array                                │
│    {                                                         │
│      "actions": [                                            │
│        {"action": "update_node", "node_id": "...", ...},    │
│        {"action": "add_edge", "source": "...", ...}         │
│      ]                                                       │
│    }                                                         │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. FlowChatAgent calls FlowModificationService              │
│    service.execute_batch_actions(                           │
│      flow=flow,                                             │
│      actions=actions,                                       │
│      flow_id=flow_id,                                       │
│      persist=True                                           │
│    )                                                         │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. FlowModificationService Executes Atomically             │
│    For each action:                                         │
│      - add_node: Adds to flow.nodes[]                       │
│      - update_node: Modifies node in flow.nodes[]           │
│      - delete_node: Removes node + auto-deletes edges       │
│      - add_edge: Adds to flow.edges[]                       │
│      - etc.                                                  │
│                                                              │
│    If ANY action fails → ROLLBACK ALL                       │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Validate Modified Flow                                   │
│    FlowCompiler.compile(modified_flow)                      │
│    - Checks for errors                                       │
│    - Validates structure                                     │
│                                                              │
│    If validation fails → ROLLBACK                           │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Persist to Database                                       │
│    repository.update_flow_with_versioning(                  │
│      session=session,                                        │
│      flow_id=flow_id,                                        │
│      new_definition=modified_flow,                           │
│      change_description="Batch modification: X nodes, Y edges",│
│      created_by="flow_chat_agent"                            │
│    )                                                         │
│                                                              │
│    Creates:                                                  │
│    - Version snapshot in flow_versions table                 │
│    - Updates flows.definition                                │
│    - Increments flows.version by 1                           │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. Returns BatchActionResult                                 │
│    BatchActionResult(                                        │
│      success=True,                                           │
│      modified_flow={...},                                    │
│      action_results=[                                        │
│        ActionResult(action_type="update_node", success=True),│
│        ActionResult(action_type="add_edge", success=True)    │
│      ]                                                       │
│    )                                                         │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. FlowChatAgent Builds Response                            │
│    if result.success:                                        │
│      summary = "Updated node 'greeting', Added edge..."      │
│      return FlowChatResponse(                                │
│        messages=[...],                                       │
│        flow_was_modified=True,                               │
│        modification_summary=summary                          │
│      )                                                       │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 9. FlowChatService Processes Response                       │
│    - Saves assistant messages to flow_chat_messages table    │
│    - Commits database transaction                            │
│    - Returns FlowChatServiceResponse                         │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 10. Returns to FlowModificationExecutor                      │
│     executor.execute() returns:                              │
│       ActionResult(                                          │
│         success=True,                                        │
│         message="✅ Fluxo modificado com sucesso!",          │
│         data={"summary": "Updated greeting node"}            │
│       )                                                      │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 11. Returns to ToolExecutionService                          │
│     ToolExecutionResult(                                     │
│       external_action_executed=True,                         │
│       external_action_result=ActionResult(...)               │
│     )                                                        │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 12. FlowTurnRunner Detects External Action                  │
│     if tool_result.requires_llm_feedback:                    │
│       # Need to inform main LLM about actual result          │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 13. FeedbackLoop.process_action_result()                    │
│     Builds feedback prompt:                                  │
│     """                                                      │
│     === EXTERNAL ACTION EXECUTION RESULT ===                │
│     Action: modify_flow                                      │
│     Status: SUCCESS                                          │
│     Result: ✅ Fluxo modificado com sucesso!                │
│     Data: {"summary": "Updated greeting node"}              │
│                                                              │
│     Generate truthful response based on ACTUAL result.       │
│     """                                                      │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 14. SECOND LLM Call (EnhancedFlowResponder)                 │
│     Input: Feedback prompt with actual result                │
│     Output: Truthful messages based on what happened         │
│     {                                                        │
│       "messages": [{                                         │
│         "text": "✅ Pronto! Modifiquei a saudação.",        │
│         "delay_ms": 0                                        │
│       }]                                                     │
│     }                                                        │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 15. Returns to FlowProcessor                                 │
│     FlowResponse(                                            │
│       result=FlowProcessingResult.CONTINUE,                  │
│       message="✅ Pronto! Modifiquei a saudação.",          │
│       metadata={"messages": [...]}                           │
│     )                                                        │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 16. WhatsApp Adapter Sends Messages                         │
│     - Extracts messages from metadata                        │
│     - Sends to user via WhatsApp                             │
│     - Applies delays between messages                        │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 17. Admin Receives Confirmation                              │
│     WhatsApp message:                                        │
│     "✅ Pronto! Modifiquei a saudação."                     │
│                                                              │
│     Flow is NOW updated in database!                         │
│     Version incremented!                                     │
│     Can test immediately!                                    │
└─────────────────────────────────────────────────────────────┘
```

## Key Points

### Two Separate Processes

**Process 1: Flow Editing (FlowChatAgent)**
- Specialized LLM that understands flow structure
- Returns batch actions
- Executes modifications
- Updates database
- Returns success/failure

**Process 2: User Communication (EnhancedFlowResponder)**  
- Main conversation LLM
- Receives actual result from Process 1
- Generates truthful user-facing messages
- Tells admin what actually happened

### Why Two LLMs?

1. **Separation of Concerns**:
   - FlowChatAgent: Expert at flow editing
   - EnhancedFlowResponder: Expert at conversation

2. **Truthfulness**:
   - FlowChatAgent might fail
   - EnhancedFlowResponder only speaks about actual results
   - No false promises

3. **Different Context**:
   - FlowChatAgent: Sees entire flow structure
   - EnhancedFlowResponder: Sees conversation context

## Error Handling at Each Stage

| Stage | Error Type | Handling |
|-------|-----------|----------|
| **LLM Call** | Timeout, invalid JSON | Retry up to 2 times, then error message |
| **Action Execution** | Invalid node ID, missing field | Rollback all, return specific error |
| **Validation** | Invalid flow structure | Rollback all, return validation errors |
| **Database** | Constraint violation, lock | Rollback all, return database error |
| **Feedback** | LLM timeout | Use fallback generic message |

All errors result in:
- ❌ No changes to database
- ❌ Original flow remains unchanged
- ✅ User receives error message explaining what went wrong

## What Gets Saved to Database

### flows table:
```sql
UPDATE flows
SET definition = '{"nodes": [...], "edges": [...]}'  -- Modified flow
    version = version + 1,                            -- Increment version
    updated_at = NOW()
WHERE id = 'flow-uuid';
```

### flow_versions table:
```sql
INSERT INTO flow_versions (
    flow_id,
    version_number,              -- New version number
    definition,                   -- Snapshot with modifications
    change_description,           -- "Batch modification: 3 nodes, 5 edges"
    created_by,                   -- "flow_chat_agent"
    created_at
) VALUES (...);
```

### flow_chat_messages table:
```sql
-- User message
INSERT INTO flow_chat_messages (flow_id, role, content)
VALUES ('flow-uuid', 'user', 'Mude a saudação...');

-- Assistant response(s)
INSERT INTO flow_chat_messages (flow_id, role, content)
VALUES ('flow-uuid', 'assistant', '✅ Pronto! Modifiquei...');
```

## Performance

| Operation | Typical Time |
|-----------|-------------|
| FlowChatAgent LLM call | ~2-3 seconds |
| Batch action execution | ~10-50ms |
| Flow validation | ~5-10ms |
| Database persistence | ~20-50ms |
| Feedback LLM call | ~1-2 seconds |
| **Total** | **~3-5 seconds** |

## Observability

Every stage logs extensively:

```
🤖 FLOW CHAT AGENT V2: Starting processing
📝 Calling repository.update_flow_with_versioning
✅ Repository update successful
📤 AGENT RESPONSE RECEIVED
🔄 FEEDBACK LOOP: Processing modify_flow result
```

Enables debugging in production!

## Summary

The Edit LLM output goes through:
1. ✅ Atomic execution (all or nothing)
2. ✅ Validation (ensures valid flow)
3. ✅ Database persistence (with versioning)
4. ✅ Feedback loop (truthful user communication)
5. ✅ Error handling (rollback on any failure)

**Result**: Safe, reliable flow modifications with proper user communication!


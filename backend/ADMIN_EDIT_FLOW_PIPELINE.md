# Admin Edit Flow Pipeline - Complete System Explanation

## Overview

The admin system has **TWO COMPLETELY SEPARATE** capabilities:

1. **Flow Modification** (`modify_flow`): Changes the flow graph structure (nodes, edges, prompts)
   - Example: "Change the greeting question to ask for name first"
   - Updates: `flows.definition` table
   - Uses: FlowChatAgent → FlowModificationService

2. **Communication Style** (`update_communication_style`): Changes HOW the bot talks (tone, formality)
   - Example: "Be more polite" or "Use more emojis"
   - Updates: `tenant.project_config.communication_style` field
   - Uses: CommunicationStyleExecutor (simple database update)

**This document explains the FLOW MODIFICATION pipeline only.** Communication style updates are much simpler and don't involve FlowChatAgent at all.

## What Happens When You Ask for a FLOW STRUCTURE Change?

### Example Request (Flow Modification - Structural)
```
Admin: "Change the greeting question to ask for their name"
```

**NOT a flow modification:**
```
Admin: "Be more polite"  ← This is communication style, different pipeline!
```

### Complete Pipeline Flow

```mermaid
graph TB
    A[Admin sends message via WhatsApp] --> B[llm_responder.py receives user message]
    B --> C[EnhancedFlowResponder.respond]
    C --> D{Is user an admin?}
    D -->|Yes| E[Add admin instructions to prompt]
    D -->|No| F[Standard flow processing]
    
    E --> G[LLM analyzes message]
    G --> H{What type of request?}
    
    H -->|Flow Modification| I[LLM decides to use PerformAction tool]
    H -->|Communication Style| J[LLM decides to use PerformAction tool]
    H -->|Regular Flow| F
    
    I --> K[PerformAction with actions: modify_flow]
    J --> L[PerformAction with actions: update_communication_style]
    
    K --> M[ToolExecutionService.execute_tool]
    L --> M
    
    NOTE: Below shows FLOW MODIFICATION path only
    Communication style path is much simpler - see separate diagram
    
    M --> N[_handle_perform_action]
    N --> O{Process each action}
    
    O -->|modify_flow| P[_handle_external_action]
    O -->|update_communication_style| P
    O -->|update/navigate/stay| Q[Internal action - execute immediately]
    
    P --> R[Get FlowModificationExecutor from ActionRegistry]
    R --> S[FlowModificationExecutor.execute]
    S --> T[FlowChatService.send_user_message]
    T --> U[FlowChatAgent.process]
    U --> V[LLM with BatchFlowActionsRequest tool]
    V --> W[Returns list of FlowActions]
    
    W --> X[FlowModificationService.execute_batch_actions]
    X --> Y{For each action}
    
    Y --> Z1[add_node]
    Y --> Z2[update_node]
    Y --> Z3[delete_node]
    Y --> Z4[add_edge]
    Y --> Z5[update_edge]
    Y --> Z6[delete_edge]
    Y --> Z7[set_entry]
    
    Z1 --> AA[Modify flow JSON in memory]
    Z2 --> AA
    Z3 --> AA
    Z4 --> AA
    Z5 --> AA
    Z6 --> AA
    Z7 --> AA
    
    AA --> AB[Validate modified flow]
    AB --> AC{Valid?}
    AC -->|Yes| AD[Persist to database via repository.update_flow_with_versioning]
    AC -->|No| AE[Rollback and return error]
    
    AD --> AF[Return ActionResult success=true]
    AE --> AG[Return ActionResult success=false]
    
    AF --> AH[FlowModificationExecutor returns ActionResult]
    AG --> AH
    
    AH --> AI[ToolExecutionResult.external_action_result = ActionResult]
    AI --> AJ{Result requires LLM feedback?}
    
    AJ -->|Yes| AK[FeedbackLoop.process_action_result]
    AK --> AL[Build feedback prompt with actual result]
    AL --> AM[LLM generates response based on ACTUAL result]
    AM --> AN[Returns messages array]
    
    AN --> AO[Messages sent to user via WhatsApp]
    AJ -->|No| AO
    
    AO --> AP[User sees confirmation or error message]
```

## Detailed Step-by-Step Breakdown

### Phase 1: Initial Detection (llm_responder.py)

**Input:**
- User message: "Change the greeting to be more professional"
- Flow context (current state, history, etc.)
- Project context (tenant info, communication style, etc.)
- `is_admin=True` flag

**What it does:**
1. `LLMFlowResponder.respond()` is called
2. Checks if user is admin
3. If admin, adds special instructions to the prompt via `_add_admin_instructions()`
4. These instructions teach the LLM about:
   - `modify_flow` action for structural changes
   - `update_communication_style` action for tone/style changes
   - Confirmation pattern (ask first, then execute)
   - How to detect admin commands vs regular answers

**Output:**
- Enhanced prompt with admin capabilities
- Passed to `EnhancedFlowResponder`

### Phase 2: LLM Decision Making (services/responder.py)

**Input:**
- Enhanced prompt with admin instructions
- User message
- Flow context
- Available tools: `PerformAction`

**What it does:**
1. LLM analyzes the request
2. Determines it's an admin command (not an answer to a flow question)
3. Decides which action(s) to take
4. For flow modifications: uses `actions=["modify_flow", "stay"]`
5. Includes:
   - `flow_modification_instruction`: Natural language instruction (Portuguese)
   - `flow_modification_target`: Optional node ID
   - `flow_modification_type`: Optional type (prompt/routing/validation/general)
   - `messages`: Messages to send to user

**Output:**
```python
{
    "tool_name": "PerformAction",
    "tool_result": {
        "metadata": {
            "actions": ["modify_flow", "stay"],
            "flow_modification_instruction": "Alterar a saudação para ser mais profissional",
            "messages": [
                {
                    "text": "Vou modificar a saudação para ser mais profissional...",
                    "delay_ms": 0
                }
            ]
        }
    }
}
```

### Phase 3: Tool Execution (services/tool_executor.py)

**Input:**
- Tool name: "PerformAction"
- Tool data with actions array
- Flow context

**What it does:**
1. `ToolExecutionService.execute_tool()` processes the tool
2. Calls `_handle_perform_action()`
3. Loops through actions:
   - Internal actions (`update`, `navigate`, `stay`) → Execute immediately
   - External actions (`modify_flow`, `update_communication_style`) → Call `_handle_external_action()`
4. For `modify_flow`:
   - Gets `FlowModificationExecutor` from `ActionRegistry`
   - Adds `flow_id` to parameters
   - Calls executor's `execute()` method

**Output:**
```python
ToolExecutionResult(
    external_action_executed=True,
    external_action_result=ActionResult(
        success=True/False,
        message="User-facing message",
        error="Technical error if failed",
        data={"summary": "What was changed"}
    )
)
```

### Phase 4: Flow Modification Execution (actions/flow_modification.py)

**Input:**
- `flow_modification_instruction`: Natural language instruction
- `flow_id`: UUID of the flow to modify
- Execution context

**What it does:**
1. `FlowModificationExecutor.execute()` validates inputs
2. Calls `_execute_modification()`
3. Creates `FlowChatAgent` with LLM client
4. Creates `FlowChatService` with database session
5. Calls `service.send_user_message(flow_id, instruction)`

**Output:**
- `ActionResult` with success status and modification summary

### Phase 5: Flow Chat Processing (services/flow_chat_service.py)

**Input:**
- Flow ID
- Instruction (natural language)
- Optional simplified view settings

**What it does:**
1. Saves user message to `flow_chat_messages` table
2. Loads flow definition from database
3. Loads chat history
4. Calls `FlowChatAgent.process()` with flow and history

**Output:**
- `FlowChatServiceResponse` with:
  - Messages from the agent
  - `flow_was_modified` boolean
  - `modification_summary` string

### Phase 6: Flow Chat Agent (agents/flow_chat_agent.py)

**Input:**
- Flow definition (JSON)
- Conversation history
- Flow ID
- Database session

**What it does:**
1. Builds comprehensive prompt explaining:
   - Flow language (nodes, edges, guards, etc.)
   - Available actions (add_node, update_node, delete_node, add_edge, etc.)
   - How to use `BatchFlowActionsRequest` tool
   - Flow structure and current state
2. Makes single LLM call with `BatchFlowActionsRequest` tool
3. LLM returns array of actions to perform
4. Processes LLM response in `_process_llm_response()`

**Output:**
```python
{
    "tool_calls": [{
        "name": "BatchFlowActionsRequest",
        "arguments": {
            "actions": [
                {
                    "action": "update_node",
                    "node_id": "greeting_node",
                    "updates": {
                        "prompt": "Boa tarde. Como posso ajudá-lo?"
                    }
                }
            ]
        }
    }]
}
```

### Phase 7: Batch Actions Execution (services/flow_modification_service.py)

**Input:**
- Flow definition (JSON)
- Array of `FlowAction` objects
- Flow ID
- Persist flag (default: True)

**What it does:**
1. Creates deep copy of flow (for atomicity)
2. Loops through each action:
   - `add_node`: Adds new node to `flow.nodes[]`
   - `update_node`: Updates existing node fields
   - `delete_node`: Removes node and connected edges
   - `add_edge`: Adds edge to `flow.edges[]`
   - `update_edge`: Updates edge properties
   - `delete_edge`: Removes edge
   - `set_entry`: Changes flow entry point
3. Validates modified flow using `FlowCompiler`
4. If valid and persist=True:
   - Calls `repository.update_flow_with_versioning()`
   - Saves to database with automatic versioning
5. If any action fails → Rollback everything

**Output:**
```python
BatchActionResult(
    success=True,
    modified_flow={...},  # Modified flow JSON
    action_results=[
        ActionResult(action_type="update_node", success=True, message="Updated node 'greeting_node'")
    ],
    error=None
)
```

### Phase 8: Database Persistence (db/repository.py)

**What happens:**
1. Updates `flows.definition` with new JSON
2. Creates new entry in `flow_versions` table
3. Increments version number
4. Stores change description
5. Commits transaction

**Result:**
- Flow is permanently updated
- Version history is preserved
- Can rollback if needed

### Phase 9: Feedback Loop (feedback/loop.py)

**Input:**
- Action name: "modify_flow"
- `ActionResult` from modification executor
- Original messages LLM wanted to send
- Original instruction

**What it does:**
1. `FeedbackLoop.process_action_result()` is called
2. Builds feedback prompt using `FeedbackPromptBuilder`
3. Creates prompt that includes:
   - Action name and result status
   - Success/failure message
   - Original instruction for context
   - What actually happened
4. Makes **second LLM call** with this feedback
5. LLM generates truthful response based on actual result
6. Returns updated messages array

**Example Prompt:**
```
=== EXTERNAL ACTION EXECUTION RESULT ===
Action: modify_flow
Status: SUCCESS
Original instruction: Alterar a saudação para ser mais profissional
Result: ✅ Fluxo modificado com sucesso! As alterações foram aplicadas.
Additional data: {"summary": "Updated node 'greeting_node' prompt"}

IMPORTANT: The action has ALREADY been executed. You must respond based on the ACTUAL result above.

Generate appropriate messages to inform the user about the result.
```

**Output:**
```python
{
    "messages": [
        {
            "text": "✅ Pronto! Alterei a saudação para ser mais profissional.",
            "delay_ms": 0
        },
        {
            "text": "A nova saudação é: 'Boa tarde. Como posso ajudá-lo?'",
            "delay_ms": 1000
        }
    ]
}
```

### Phase 10: Response to User (runner.py → WhatsApp)

**What happens:**
1. `FlowTurnRunner` receives final `ToolExecutionResult`
2. Extracts messages from metadata
3. Returns to flow processor
4. Flow processor returns `FlowResponse`
5. WhatsApp adapter sends messages to user

**User receives:**
```
✅ Pronto! Alterei a saudação para ser mais profissional.
A nova saudação é: 'Boa tarde. Como posso ajudá-lo?'
```

## Key Components Summary

### 1. **LLMFlowResponder** (`llm_responder.py`)
- Entry point for LLM-based responses
- Wraps `EnhancedFlowResponder`
- Converts output to unified `FlowResponse` format

### 2. **EnhancedFlowResponder** (`services/responder.py`)
- Main LLM interaction layer
- Adds admin instructions when needed
- Returns tool calls and messages

### 3. **ToolExecutionService** (`services/tool_executor.py`)
- Executes tool calls from LLM
- Separates internal vs external actions
- Handles `PerformAction` tool with multiple action types

### 4. **ActionRegistry** (`actions/registry.py`)
- Maps action names to executors
- Registers `FlowModificationExecutor`, `CommunicationStyleExecutor`, etc.

### 5. **FlowModificationExecutor** (`actions/flow_modification.py`)
- Bridges tool execution and flow modification
- Creates `FlowChatAgent` and `FlowChatService`
- Returns `ActionResult`

### 6. **FlowChatService** (`services/flow_chat_service.py`)
- Orchestrates flow chat conversation
- Manages database persistence of chat messages
- Calls agent and handles responses

### 7. **FlowChatAgent** (`agents/flow_chat_agent.py`)
- Specialized LLM agent for flow editing
- Uses single tool call with batch actions
- Handles retries and errors

### 8. **FlowModificationService** (`services/flow_modification_service.py`)
- Core flow modification logic
- Executes atomic batch actions
- Validates and persists changes

### 9. **FeedbackLoop** (`feedback/loop.py`)
- Ensures LLM knows actual results
- Prevents false promises
- Generates truthful user messages

### 10. **FlowTurnRunner** (`runner.py`)
- Orchestrates entire turn processing
- Manages feedback loops
- Returns final results

## Data Flow Summary

```
User Input (WhatsApp)
    ↓
LLMFlowResponder (receives request, checks admin status)
    ↓
EnhancedFlowResponder (LLM decides action)
    ↓
ToolExecutionService (routes to appropriate executor)
    ↓
FlowModificationExecutor (creates agent/service)
    ↓
FlowChatService (manages persistence)
    ↓
FlowChatAgent (LLM generates batch actions)
    ↓
FlowModificationService (executes actions atomically)
    ↓
Database (update_flow_with_versioning)
    ↓
ActionResult (success/failure)
    ↓
FeedbackLoop (LLM generates truthful response)
    ↓
Messages Array
    ↓
WhatsApp Adapter
    ↓
User Output (WhatsApp)
```

## Input/Output at Each Stage

| Component | Input | Output |
|-----------|-------|--------|
| **LLMFlowResponder** | User message, context, config | `UnifiedFlowResponse` |
| **EnhancedFlowResponder** | Prompt, context, user message | `ResponderOutput` (tool + messages) |
| **ToolExecutionService** | Tool name, tool data, context | `ToolExecutionResult` |
| **FlowModificationExecutor** | Instruction, flow_id, context | `ActionResult` |
| **FlowChatService** | Flow ID, instruction | `FlowChatServiceResponse` |
| **FlowChatAgent** | Flow def, history, flow ID | `FlowChatResponse` |
| **FlowModificationService** | Flow, actions array, flow ID | `BatchActionResult` |
| **FeedbackLoop** | Action result, context | Updated messages array |

## Important Notes

### Why Two LLM Calls?

1. **First LLM Call** (EnhancedFlowResponder):
   - Decides what action to take
   - Generates *intended* messages
   - Doesn't know if action will succeed

2. **Second LLM Call** (FeedbackLoop):
   - Receives *actual* action result
   - Generates truthful messages
   - Only speaks about what actually happened

### Atomic Transactions

- All flow modifications are atomic
- If any action fails, entire batch is rolled back
- Database transaction ensures consistency

### Version Control

- Every modification creates a new version
- Can rollback to previous versions
- Change descriptions are stored

### Error Handling

- Each layer has comprehensive error handling
- Errors propagate up with context
- User sees appropriate error messages
- Technical errors are logged but not exposed

### Admin Detection

- Based on phone number in `Tenant.admin_phone_numbers`
- Checked at flow processor level
- Admin instructions only added for confirmed admins

## Confirmation Pattern

For safety, admin commands follow a two-step confirmation:

1. **First message**: Admin makes request
   - LLM: "Entendi! Vou [explain change]. Posso prosseguir?"
   - Uses `actions=["stay"]` (no execution yet)

2. **Second message**: Admin confirms
   - User: "Sim" or "Confirmo"
   - LLM: Executes with `actions=["modify_flow", "stay"]`
   - Actual modification happens

This prevents accidental changes and gives admins a chance to review.

## Example Complete Flow

### Request
```
Admin: "Divide o nó de coleta de dados em 3 perguntas separadas"
```

### Step 1: LLM Decides
```python
PerformAction(
    actions=["stay"],
    messages=[{
        "text": "Vou dividir o nó de coleta em 3 perguntas separadas:\n1. Nome\n2. Email\n3. Telefone\n\nPosso prosseguir?"
    }],
    reasoning="Admin requesting clarification before execution"
)
```

### Step 2: Admin Confirms
```
Admin: "Sim"
```

### Step 3: LLM Executes
```python
PerformAction(
    actions=["modify_flow", "stay"],
    flow_modification_instruction="Dividir o nó 'coleta_dados' em 3 nós separados para nome, email e telefone",
    flow_modification_target="coleta_dados",
    flow_modification_type="prompt",
    messages=[{
        "text": "Modificando o fluxo..."
    }]
)
```

### Step 4: Batch Actions Generated
```python
BatchFlowActionsRequest(
    actions=[
        {"action": "delete_node", "node_id": "coleta_dados"},
        {"action": "add_node", "node_definition": {...}},  # nome_node
        {"action": "add_node", "node_definition": {...}},  # email_node
        {"action": "add_node", "node_definition": {...}},  # telefone_node
        {"action": "add_edge", "source": "nome_node", "target": "email_node"},
        {"action": "add_edge", "source": "email_node", "target": "telefone_node"},
    ]
)
```

### Step 5: Database Updated
- Flow definition updated
- New version created
- Changes persisted

### Step 6: Feedback Generated
```python
{
    "messages": [{
        "text": "✅ Pronto! Dividi o nó em 3 perguntas separadas:\n• Nome\n• Email\n• Telefone"
    }]
}
```

### User Sees
```
✅ Pronto! Dividi o nó em 3 perguntas separadas:
• Nome
• Email
• Telefone
```

## Architecture Benefits

1. **Separation of Concerns**: Each component has single responsibility
2. **Type Safety**: Strong typing throughout the pipeline
3. **Testability**: Each layer can be tested independently
4. **Observability**: Comprehensive logging at every step
5. **Error Resilience**: Multiple layers of error handling
6. **Truthfulness**: Feedback loop prevents false promises
7. **Atomicity**: All-or-nothing modifications
8. **Versioning**: Complete change history
9. **Extensibility**: Easy to add new action types
10. **Production Ready**: Battle-tested with real users


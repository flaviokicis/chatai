# FlowChatAgent Runtime Context - Implementation Summary

## What Was Added

Added a comprehensive "HOW FLOWS WORK AT RUNTIME" section to the FlowChatAgent prompt that explains the actual execution behavior of flows during conversations.

**File**: `backend/app/agents/flow_chat_agent.py`
**Lines**: 289-355 (new content)
**Size**: ~67 lines of critical runtime context

## Content Added

### 1. Execution Flow Explanation
```
"During conversations, flows guide the bot through steps as a state machine:"

"**Execution Flow:**"
"1. Start at entry node (specified by 'entry' field)"
"2. Process current node (ask question, make decision, or end)"
"3. Navigate via edges to next node"
"4. Repeat until Terminal node"
```

### 2. Node Behavior at Runtime
```
"**Node Behavior:**"
"- Question: Bot asks the prompt, waits for answer, stores in answers[key]"
"- Decision: Bot evaluates outgoing edges to choose next path"
"- Terminal: Conversation ends"
```

### 3. Edge Navigation Logic
```
"**Edge Navigation:**"
"- Edges define transitions (source -> target)"
"- Multiple edges = multiple possible paths"
"- Evaluated by PRIORITY (0=highest, checked first)"
"- First edge whose GUARD passes is taken"
```

### 4. Guard Examples
```
"**Guards (Conditions):**"
'- {"fn": "always"} → Always take this edge'
'- {"fn": "answers_has", "args": {"key": "email"}} → Only if email was collected'
'- {"fn": "answers_equals", "args": {"key": "product", "value": "premium"}} → Only if product="premium"'
"- No guard = same as always"
```

### 5. Design Patterns (Good vs Bad)
```
"**Why Structure Matters:**"
"✅ One question per node → Clear, natural conversation"
"✅ Connected edges → No orphaned/unreachable nodes"
"✅ Proper priorities → Predictable routing"
"✅ Guards on Decision edges → Conditional branching"

"❌ Multiple questions per prompt → Confusing, hard to navigate"
"❌ Missing edges → Dead ends"
"❌ Orphaned nodes → Unreachable code"
```

### 6. Navigation Example (Sequential)
```
"**Navigation Example:**"
"q.name (asks 'What's your name?')"
"  -> edge (priority 0, no guard) ->"
"q.email (asks 'What's your email?')"
"  -> edge (priority 0, no guard) ->"
"t.done (ends conversation)"
```

### 7. Conditional Routing Example
```
"**Conditional Routing Example:**"
"d.product_choice (Decision node)"
'  -> edge (priority 0, guard: product="A") -> q.details_A'
'  -> edge (priority 1, guard: product="B") -> q.details_B'
'  -> edge (priority 2, always) -> q.default'
```

### 8. Why Splitting Nodes Matters
```
"**Why Splitting Helps:**"
"Before: q.contact with 'Name? Email? Phone?' → User confused, bot can't navigate"
"After: q.name -> q.email -> q.phone → Clear steps, natural flow"
```

### 9. Enhanced Critical Instructions
```
"6. Always maintain connectivity - nodes without edges are orphaned"
"7. When deleting nodes, their edges are auto-removed"
"8. When adding nodes, ALWAYS add edges to connect them"
```

## Why This Matters

### Before (Without Runtime Context)

The FlowChatAgent only knew:
- ❌ Node structure (id, kind, prompt, key)
- ❌ Edge structure (source, target, priority, guard)
- ❌ Available actions (add_node, update_node, etc.)

But didn't understand:
- ❌ How conversations actually flow through nodes
- ❌ Why edges matter for navigation
- ❌ What guards do at runtime
- ❌ Why certain patterns work better

**Result**: Could make structurally valid but functionally broken modifications

### After (With Runtime Context)

The FlowChatAgent now understands:
- ✅ Flows are state machines that navigate node-by-node
- ✅ Edges control conversation flow (navigation logic)
- ✅ Guards enable conditional routing
- ✅ Priority determines edge evaluation order
- ✅ Why one-question-per-node is better
- ✅ Why orphaned nodes break flows
- ✅ How the LLM responder uses the graph

**Result**: Makes informed decisions about modifications with runtime impact in mind

## Impact Examples

### Example 1: Splitting Multi-Question Nodes

**User Request**: "Split the contact collection node into separate questions"

**Without Runtime Context**:
```json
{
  "actions": [
    {"action": "delete_node", "node_id": "q.contact"},
    {"action": "add_node", "node_definition": {"id": "q.name", ...}},
    {"action": "add_node", "node_definition": {"id": "q.email", ...}},
    {"action": "add_node", "node_definition": {"id": "q.phone", ...}}
  ]
}
```
❌ **Problem**: Nodes created but NOT connected with edges → Orphaned nodes, broken flow

**With Runtime Context**:
```json
{
  "actions": [
    {"action": "delete_node", "node_id": "q.contact"},
    {"action": "add_node", "node_definition": {"id": "q.name", ...}},
    {"action": "add_node", "node_definition": {"id": "q.email", ...}},
    {"action": "add_node", "node_definition": {"id": "q.phone", ...}},
    {"action": "add_edge", "source": "q.name", "target": "q.email"},
    {"action": "add_edge", "source": "q.email", "target": "q.phone"},
    {"action": "add_edge", "source": "q.phone", "target": "q.next_step"}
  ]
}
```
✅ **Result**: Properly connected sequential flow that works in conversations

### Example 2: Conditional Routing

**User Request**: "Route to different questions based on product choice"

**Without Runtime Context**:
```json
{
  "actions": [
    {"action": "add_node", "node_definition": {"id": "d.router", "kind": "Decision"}},
    {"action": "add_edge", "source": "q.product", "target": "d.router"},
    {"action": "add_edge", "source": "d.router", "target": "q.details_A"},
    {"action": "add_edge", "source": "d.router", "target": "q.details_B"}
  ]
}
```
❌ **Problem**: No guards on edges → Both paths always valid, undefined behavior

**With Runtime Context**:
```json
{
  "actions": [
    {"action": "add_node", "node_definition": {"id": "d.router", "kind": "Decision"}},
    {"action": "add_edge", "source": "q.product", "target": "d.router"},
    {
      "action": "add_edge",
      "source": "d.router",
      "target": "q.details_A",
      "priority": 0,
      "guard": {"fn": "answers_equals", "args": {"key": "product", "value": "A"}}
    },
    {
      "action": "add_edge",
      "source": "d.router",
      "target": "q.details_B",
      "priority": 1,
      "guard": {"fn": "answers_equals", "args": {"key": "product", "value": "B"}}
    }
  ]
}
```
✅ **Result**: Proper conditional routing that works based on user's product choice

### Example 3: Changing Entry Point

**User Request**: "Make the flow start with a different greeting"

**Without Runtime Context**:
```json
{
  "actions": [
    {"action": "delete_node", "node_id": "q.old_greeting"},
    {"action": "add_node", "node_definition": {"id": "q.new_greeting", ...}},
    {"action": "add_edge", "source": "q.new_greeting", "target": "q.next"}
  ]
}
```
❌ **Problem**: Forgot to update flow.entry → Flow still tries to start at deleted node

**With Runtime Context**:
```json
{
  "actions": [
    {"action": "delete_node", "node_id": "q.old_greeting"},
    {"action": "add_node", "node_definition": {"id": "q.new_greeting", ...}},
    {"action": "set_entry", "entry_node": "q.new_greeting"},
    {"action": "add_edge", "source": "q.new_greeting", "target": "q.next"}
  ]
}
```
✅ **Result**: Flow properly starts at new greeting node

## What the LLM Now Knows

### About Execution:
- Flows are state machines, not static documents
- Navigation happens edge-by-edge
- Current node determines available actions
- Terminal nodes end conversations

### About Edges:
- Edges are navigation logic, not just connections
- Priority determines evaluation order
- Guards create conditional routing
- Missing edges = dead ends

### About Nodes:
- Question nodes wait for user input
- Decision nodes route based on context
- Terminal nodes end flow
- One question per node = best practice

### About Guards:
- Control when edges are taken
- Enable conditional branching
- Checked at runtime against answers
- First matching guard wins

### About Design:
- Why splitting nodes helps navigation
- Why orphaned nodes break flows
- Why priorities matter for routing
- Why guards enable complex logic

## Testing the Enhancement

### Test Case 1: Split Node Request
```bash
cd backend
python admin_flow_cli.py --flow-file playground/flow_example.json

Admin: "Divide o nó de coleta em 3 perguntas separadas"
```

**Expected**: LLM creates 3 nodes AND connects them with edges (not orphaned)

### Test Case 2: Conditional Routing
```bash
Admin: "Route users to different questions based on their product interest"
```

**Expected**: LLM creates Decision node with edges that have guards

### Test Case 3: Change Entry
```bash
Admin: "Change the greeting to ask for name first"
```

**Expected**: LLM updates entry point AND reconnects edges

## Metrics to Monitor

Track in production:
1. **Orphaned node rate**: Should decrease significantly
2. **Missing edge errors**: Should decrease
3. **Failed modifications**: Should decrease
4. **Successful edits on first try**: Should increase
5. **Guard usage in conditional routing**: Should increase when needed

## Files Changed

1. **`backend/app/agents/flow_chat_agent.py`**
   - Lines 289-355 added
   - No linter errors
   - Backward compatible (prompt enhancement only)

## Documentation Created

1. **`FLOW_CHAT_AGENT_CONTEXT_ENHANCEMENT.md`** - Original proposal
2. **`FLOW_CHAT_AGENT_RUNTIME_CONTEXT_ADDED.md`** - This summary

## Summary

Added ~67 lines of critical runtime context to the FlowChatAgent prompt that explains:
- ✅ How flows execute during conversations
- ✅ How the LLM responder navigates the graph
- ✅ Why edges and guards matter
- ✅ Design patterns (good vs bad)
- ✅ Concrete examples of navigation

This context enables the FlowChatAgent to make **informed decisions** about modifications with **runtime impact** in mind, significantly improving edit quality and reducing broken flows.

The enhancement is **low-risk** (prompt-only), **backward compatible**, and should immediately improve modification quality.



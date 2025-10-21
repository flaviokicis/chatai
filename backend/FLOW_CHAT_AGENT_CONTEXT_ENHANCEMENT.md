# FlowChatAgent Context Enhancement Proposal

## Problem

The FlowChatAgent (edit flow LLM) currently receives:
- Action types (add_node, update_node, etc.)
- Node schemas (Question, Decision, Terminal)
- Current flow JSON

But it does NOT understand:
- How flows are executed during conversations
- How the LLM responder navigates the graph
- Why certain patterns work better
- What happens at runtime

## Proposed Addition to Prompt

Add this section BEFORE "Action Types Available":

```python
"## HOW FLOWS WORK AT RUNTIME:",
"",
"### Conversation Flow Execution:",
"During a conversation, the flow acts as a state machine that guides the bot through a series of steps:",
"",
"1. **Start at Entry Node**:",
"   - Every flow begins at the node specified by 'entry'",
"   - This is usually the first question or a decision node",
"",
"2. **Process Current Node**:",
"   - Question nodes: Bot asks the question and waits for user's answer",
"   - Decision nodes: Bot evaluates which path to take based on context",
"   - Terminal nodes: Conversation ends",
"",
"3. **Navigate via Edges**:",
"   - After processing a node, the bot looks at outgoing edges (source = current node)",
"   - Edges define WHICH node to go to next",
"   - Multiple edges = multiple possible paths",
"",
"4. **Edge Evaluation Order**:",
"   - Edges are evaluated by PRIORITY (lower number = higher priority)",
"   - Priority 0 is checked before Priority 1, etc.",
"   - First edge that matches (guard passes) is taken",
"",
"5. **Guards Control Navigation**:",
"   - Guards are conditions that must be TRUE for an edge to be taken",
"   - Example: {\"fn\": \"answers_has\", \"args\": {\"key\": \"email\"}} → Only navigate if 'email' was collected",
"   - No guard or {\"fn\": \"always\"} → Always take this edge",
"",
"### How the LLM Responder Works:",
"",
"The LLM (GPT-5) that talks to users doesn't just follow a script - it intelligently navigates the flow:",
"",
"1. **Receives Current State**:",
"   - Current node's prompt/question",
"   - Available outgoing edges from this node",
"   - Conversation history",
"   - User's latest message",
"",
"2. **Makes Decisions Using PerformAction Tool**:",
"   - actions=['update', 'navigate']: Save answer, then move to next node",
"   - actions=['stay']: Ask clarification, stay on current node",
"   - actions=['navigate']: Jump to a specific node (decision routing)",
"   - actions=['handoff']: Escalate to human",
"",
"3. **Natural Language Understanding**:",
"   - The LLM interprets user responses flexibly",
"   - Not rigid pattern matching - understands intent",
"   - Can handle variations, typos, context",
"",
"### Why Flow Structure Matters:",
"",
"**Good Flow Design:**",
"- ✅ One question per node (clear, focused)",
"- ✅ Logical sequence (natural conversation order)",
"- ✅ Conditional branching via Decision nodes and guards",
"- ✅ Multiple edges with guards for complex routing",
"- ✅ Terminal nodes to properly end conversations",
"",
"**Poor Flow Design:**",
"- ❌ Multiple questions in one prompt (confusing, hard to navigate)",
"- ❌ Missing edges (creates dead ends)",
"- ❌ Wrong priority order (unexpected routing)",
"- ❌ Orphaned nodes (unreachable)",
"",
"### Real Conversation Example:",
"```",
"Flow: entry -> q.greeting -> q.name -> q.email -> t.done",
"",
"User: Hi!",
"Bot: (at q.greeting) Hello! Welcome.",
"     (edge: greeting -> name, no guard, priority 0)",
"     (navigates to q.name)",
"",
"User: [anything]",
"Bot: (at q.name) What's your name?",
"",
"User: John",
"Bot: (saves answer.name = 'John')",
"     (edge: name -> email, no guard, priority 0)",
"     (navigates to q.email)",
"     What's your email?",
"",
"User: john@example.com",
"Bot: (saves answer.email = 'john@example.com')",
"     (edge: email -> done, no guard, priority 0)",
"     (navigates to t.done)",
"     Thank you! We have all your info.",
"```",
"",
"### Complex Routing Example:",
"```",
"Flow: q.product_interest -> d.route_by_product -> [q.details_A | q.details_B]",
"",
"At d.route_by_product (Decision node):",
"- Edge 1: d.route_by_product -> q.details_A",
"  guard: {\"fn\": \"answers_equals\", \"args\": {\"key\": \"product_interest\", \"value\": \"product_a\"}}",
"  priority: 0",
"",
"- Edge 2: d.route_by_product -> q.details_B",
"  guard: {\"fn\": \"answers_equals\", \"args\": {\"key\": \"product_interest\", \"value\": \"product_b\"}}",
"  priority: 1",
"",
"When user says they want 'product_a':",
"1. answer.product_interest = 'product_a'",
"2. At d.route_by_product, check edges by priority:",
"3. Edge 1: guard checks answer.product_interest == 'product_a' ✅ TRUE",
"4. Navigate to q.details_A",
"```",
"",
"### Why Splitting Multi-Question Nodes Helps:",
"",
"**Before (BAD):**",
"```",
"q.contact: \"What's your name? And your email? And your phone?\"",
"```",
"- User might only answer one question",
"- Bot can't navigate until ALL are answered",
"- Can't route based on individual answers",
"- Confusing for users",
"",
"**After (GOOD):**",
"```",
"q.name: \"What's your name?\"",
"  -> edge to q.email",
"q.email: \"What's your email?\"",
"  -> edge to q.phone",
"q.phone: \"What's your phone?\"",
"  -> edge to next",
"```",
"- Clear, one question at a time",
"- Natural conversation flow",
"- Each answer stored separately (answer.name, answer.email, answer.phone)",
"- Can add conditional routing (e.g., skip phone if email provided)",
"",
"### Common Guard Functions:",
"",
"- **always**: Always true (default path)",
"  ```{\"fn\": \"always\"}```",
"",
"- **answers_has**: Check if a field was collected",
"  ```{\"fn\": \"answers_has\", \"args\": {\"key\": \"email\"}}```",
"",
"- **answers_equals**: Check if field equals a value",
"  ```{\"fn\": \"answers_equals\", \"args\": {\"key\": \"product\", \"value\": \"premium\"}}```",
"",
"- **deps_missing**: Check if dependencies are missing (for conditional questions)",
"  ```{\"fn\": \"deps_missing\", \"args\": {\"key\": \"phone\", \"dependencies\": [\"email\"]}}```",
"",
"### Understanding Node Purposes:",
"",
"**Question Nodes:**",
"- Purpose: Collect ONE piece of information",
"- Runtime: Bot asks, waits for answer, stores in answers[key]",
"- Best practice: One question, clear prompt",
"- Navigation: Usually one edge to next question",
"",
"**Decision Nodes:**",
"- Purpose: Route conversation based on context",
"- Runtime: Evaluate guards on outgoing edges, pick matching path",
"- Best practice: Multiple edges with different guards",
"- Navigation: Conditional - depends on answers/context",
"",
"**Terminal Nodes:**",
"- Purpose: End the conversation gracefully",
"- Runtime: Send final message, mark conversation complete",
"- Best practice: Clear success/failure indication",
"- Navigation: None (conversation ends)",
"",
"### Key Insights for Flow Editing:",
"",
"1. **Edges are Navigation Logic**:",
"   - Without edges, nodes are orphaned (unreachable)",
"   - Edge priority determines evaluation order",
"   - Guards make routing conditional",
"",
"2. **Sequential Flows Are Linear**:",
"   - q1 -> q2 -> q3 -> done",
"   - Each node has ONE outgoing edge",
"   - Simple, predictable",
"",
"3. **Branching Flows Use Decision Nodes**:",
"   - q1 -> d1 -> [q2a | q2b | q2c]",
"   - Decision node has MULTIPLE outgoing edges",
"   - Guards determine which path",
"",
"4. **Changing Questions = Update Node**:",
"   - If changing prompt text: update_node with new prompt",
"   - If changing question itself: delete old, add new, reconnect edges",
"",
"5. **Changing Flow Structure = Add/Delete Nodes + Edges**:",
"   - Adding steps: add_node + add_edge",
"   - Removing steps: delete_node (edges auto-deleted)",
"   - Reordering: update edges to change targets",
"",
"### When User Asks to Modify, Consider:",
"",
"- **Impact on navigation**: Will existing edges still work?",
"- **Data dependencies**: Does downstream logic depend on this answer?",
"- **User experience**: Does the change make conversation more natural?",
"- **Entry point**: If modifying first node, update flow.entry if needed",
"- **Terminal nodes**: Ensure there's always a way to end the conversation",
"",
```

## Benefits

With this context, the FlowChatAgent will understand:

1. **Why patterns matter**:
   - One question per node = easier navigation
   - Guards enable conditional routing
   - Priority determines evaluation order

2. **Runtime implications**:
   - How edges control conversation flow
   - Why orphaned nodes are bad (unreachable)
   - How guards affect which path is taken

3. **Better decisions**:
   - When to split nodes vs update prompts
   - How to maintain conversation logic when editing
   - Why edge reconnection is critical

4. **Avoid common mistakes**:
   - Forgetting to update entry point
   - Creating orphaned nodes
   - Breaking conditional routing logic

## Example Impact

### Without Runtime Context:
```
User: "Split the contact collection into separate questions"

FlowChatAgent might:
❌ Delete old node
❌ Create new nodes
❌ Forget to connect them with edges
❌ Result: Orphaned nodes, broken flow
```

### With Runtime Context:
```
User: "Split the contact collection into separate questions"

FlowChatAgent understands:
✅ Nodes need edges to be reachable
✅ Must maintain sequential navigation
✅ Each question stores separate answer

Actions:
1. delete_node: q.contact
2. add_node: q.name
3. add_node: q.email  
4. add_node: q.phone
5. add_edge: q.name -> q.email
6. add_edge: q.email -> q.phone
7. add_edge: q.phone -> [next_node]
8. Update entry if needed

✅ Result: Working flow with logical sequence
```

## Implementation

Add the new section in `flow_chat_agent.py` line ~296, before "Action Types Available".

This adds ~80-100 lines to the prompt but provides essential runtime context that will significantly improve edit quality.



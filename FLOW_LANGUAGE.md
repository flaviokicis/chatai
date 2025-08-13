### Flow Language (v2)

This document specifies the Flow IR used by the backend flow engine. Flows are authored as JSON (schema_version v2), compiled by `backend/app/flow_core/compiler.py` into a `CompiledFlow`, and executed by `backend/app/flow_core/engine.py` with state in `backend/app/flow_core/state.py`.

## IR Overview

- **Flow**

  - `schema_version`: "v2"
  - `id`: string
  - `entry`: string (node id)
  - `metadata?`: name, description, version, author, tags, timestamps
  - `nodes`: array of nodes (see below)
  - `edges`: array of edges (see below)
  - `policies?`: path_selection, conversation, validation
  - `validations?`: dict of ValidationRule by key
  - `context?`: dict for global constants/vars
  - `subflows?`: dict of nested Flow(s) keyed by name

- **Node kinds** (all nodes share: `id`, `kind`, `label?`, `meta?`, `skippable?`, `revisitable?`, `max_attempts?`)

  - QuestionNode (`kind: "Question"`)
    - `key`: string (answer key in `ctx.answers`)
    - `prompt`: string
    - `validator?`: string (named validation; engine-side custom registry TBD)
    - `clarification?`: string
    - `examples?`: string[]
    - `allowed_values?`: string[]
    - `data_type?`: "text" | "number" | "boolean" | "date" | "email" | "phone" | "url"
    - `required?`: boolean (default True)
    - `dependencies?`: string[] (keys this question depends on)
    - `priority?`: number (lower = earlier when engine chooses next)
  - DecisionNode (`kind: "Decision"`)
    - `decision_type?`: "automatic" | "llm_assisted" | "user_choice"
    - `decision_prompt?`: string
  - TerminalNode (`kind: "Terminal"`)
    - `reason?`: string
    - `success?`: boolean
    - `next_flow?`: string
    - `handoff_required?`: boolean
  - ActionNode (`kind: "Action"`)
    - `action_type`: string
    - `action_config?`: object
    - `output_keys?`: string[]
  - SubflowNode (`kind: "Subflow"`)
    - `flow_ref`: string (key in `subflows`)
    - `input_mapping?`: dict parent_key -> child_key
    - `output_mapping?`: dict child_key -> parent_key

- **Edge**

  - `source`: node id
  - `target`: node id
  - `priority?`: number (ascending evaluation order)
  - `guard?`: GuardRef
  - `label?`: string (for UI)
  - `condition_description?`: string (human-readable condition)

- **GuardRef**

  - `fn`: string (see guard catalog)
  - `args?`: dict (function-specific arguments; can carry LLM hints like `{"if": "..."}` for LLM-assisted choices)
  - `description?`: string (LLM hint)
  - `weight?`: number (LLM hint)

- **Policies** (optional)

  - `path_selection`: `{ lock_threshold, allow_switch_before_lock, confidence_threshold, use_llm }`
  - `conversation`: `{ allow_clarifications, max_clarifications, allow_skip, allow_revisit, conversation_style, use_examples, maintain_context }`
  - `validation`: `{ strict_validation, max_validation_attempts, validation_strategy }`

- **ValidationRule** (optional)
  - `type`: "regex" | "range" | "length" | "custom"
  - `pattern?`, `min_value?`, `max_value?`, `min_length?`, `max_length?`, `function?`, `error_message?`

## Guard catalog (`backend/app/flow_core/guards.py`)

- **always()**
  - Args: none
  - True unconditionally
- **answers_has({ key })**
  - True if `ctx.answers[key]` is non-empty
- **answers_equals({ key, value, allowed_values? })**
  - True if `ctx.answers[key] === value`, or if both are strings and `allowed_values` provided, a fuzzy canonical match equals `value`.
  - LLM-first flows typically avoid this and instead use LLM-assisted decisions (see example below). Use when you need strict gating.
- **path_locked()**
  - True if `ctx.path_locked` and `ctx.active_path` set
- **deps_missing({ key, dependencies })**
  - True if all dependency keys are present (non-empty) and `ctx.answers[key]` is empty

## Runtime semantics (engine)

- **Entry**: starts at `flow.entry` node id.
- **Question nodes**
  - Engine sets `ctx.pending_field = node.key` and returns a prompt.
  - If an event includes `"answer"`, it stores `answers[key]` and advances via outgoing edges (guards by priority). If no edge matches, the engine may select the next appropriate question (LLM or priority).
  - Tool events (see below) can skip, revisit, navigate, or escalate.
  - Prompt text may be adapted by conversation style/history when an LLM is configured.
- **Decision nodes**
  - Strict mode: first edge with guard True.
  - Flexible mode (default): may ask LLM to choose among edges; otherwise falls back to first guard-True edge.
- **Terminal nodes**
  - Marks complete and returns final answers in metadata.
- **Next-question discovery**
  - If no valid outgoing edge, engine can pick next unanswered question (by LLM or `priority`). You can also model a “chooser” Decision node using `deps_missing` guards.

## Tool events (engine-level handling)

- **UnknownAnswer**: skips optional questions; escalates if the question is required or `meta.escalate_on_unknown`.
- **SkipQuestion**: marks skipped; optional `skip_to` target id.
- **RevisitQuestion**: jump to another question or directly update a prior answer.
- **RequestHumanHandoff**: escalates.
- **ProvideInformation**: informational; remain on current node.
- **ConfirmCompletion**: produce terminal completion.
- **NavigateFlow**: jump to target node.
- **UpdateAnswersFlow**: typically applied by the runner/responder before re-entering the engine; when updating the current pending field it appears as `{"answer": ...}` in the engine event.

## Example: sales flow (v2 JSON, LLM-first)

```json
{
  "schema_version": "v2",
  "id": "flow.sales_example",
  "entry": "d.start",
  "metadata": { "name": "Sales Example", "version": "1.0.0" },
  "policies": {
    "path_selection": { "lock_threshold": 2, "allow_switch_before_lock": true },
    "conversation": {
      "allow_clarifications": true,
      "allow_skip": false,
      "conversation_style": "adaptive"
    },
    "validation": { "strict_validation": false }
  },
  "nodes": [
    { "id": "d.start", "kind": "Decision", "label": "Start" },
    {
      "id": "q.use_case",
      "kind": "Question",
      "key": "use_case",
      "prompt": "Which best describes your project?",
      "priority": 20
    },
    {
      "id": "d.route_use_case",
      "kind": "Decision",
      "label": "Route by use_case",
      "decision_type": "llm_assisted",
      "decision_prompt": "Choose the next branch based on the user's described project."
    },
    {
      "id": "q.court_type",
      "kind": "Question",
      "key": "court_type",
      "prompt": "Is it indoor or outdoor?",
      "priority": 30,
      "dependencies": ["use_case"]
    },
    {
      "id": "q.dimensions",
      "kind": "Question",
      "key": "dimensions",
      "prompt": "Do you know the court dimensions?",
      "priority": 40,
      "dependencies": ["court_type"]
    },
    {
      "id": "q.field_size",
      "kind": "Question",
      "key": "field_size",
      "prompt": "Approximate field size?",
      "priority": 30,
      "dependencies": ["use_case"]
    },
    {
      "id": "q.surface",
      "kind": "Question",
      "key": "surface",
      "prompt": "Surface type?",
      "priority": 40,
      "dependencies": ["field_size"]
    },
    {
      "id": "q.lighting_level",
      "kind": "Question",
      "key": "lighting_level",
      "prompt": "Target lighting level (lux), if any?",
      "data_type": "number",
      "priority": 50
    },
    {
      "id": "q.budget",
      "kind": "Question",
      "key": "budget",
      "prompt": "Do you have a budget range in mind?",
      "priority": 90
    },
    {
      "id": "q.timeframe",
      "kind": "Question",
      "key": "timeframe",
      "prompt": "What is your ideal timeline?",
      "priority": 100
    },
    { "id": "t.done", "kind": "Terminal", "reason": "complete" }
  ],
  "edges": [
    { "source": "d.start", "target": "q.intention", "priority": 0 },
    {
      "source": "q.intention",
      "target": "q.use_case",
      "guard": { "fn": "answers_has", "args": { "key": "intention" } },
      "priority": 0
    },
    {
      "source": "q.use_case",
      "target": "d.route_use_case",
      "priority": 0
    },

    {
      "source": "d.route_use_case",
      "target": "q.court_type",
      "guard": {
        "fn": "always",
        "args": { "if": "project resembles a court/tennis use-case" }
      },
      "priority": 0,
      "condition_description": "If the user's project sounds like a court/tennis project, go to court details"
    },
    {
      "source": "d.route_use_case",
      "target": "q.field_size",
      "guard": {
        "fn": "always",
        "args": { "if": "project resembles a field/soccer use-case" }
      },
      "priority": 1,
      "condition_description": "If the user's project sounds like a field/soccer project, go to field details"
    },

    { "source": "q.court_type", "target": "q.dimensions", "priority": 0 },
    { "source": "q.dimensions", "target": "q.lighting_level", "priority": 0 },
    { "source": "q.field_size", "target": "q.surface", "priority": 0 },
    { "source": "q.surface", "target": "q.lighting_level", "priority": 0 },
    { "source": "q.lighting_level", "target": "q.budget", "priority": 0 },
    { "source": "q.budget", "target": "q.timeframe", "priority": 0 },
    { "source": "q.timeframe", "target": "t.done", "priority": 0 }
  ],
  "validations": {
    "budget": {
      "type": "regex",
      "pattern": "^\\$?\\d+(?:\\s*-\\s*\\$?\\d+)?$",
      "error_message": "Please provide a budget like 5000 or $5000 - $10000."
    }
  },
  "context": {}
}
```

## Minimal TypeScript types (for a visual editor)

```ts
export type NodeKind =
  | "Question"
  | "Decision"
  | "Terminal"
  | "Action"
  | "Subflow";

export interface GuardRef {
  fn:
    | "always"
    | "answers_has"
    | "answers_equals"
    | "path_locked"
    | "deps_missing"
    | (string & {});
  args?: Record<string, unknown>;
  description?: string | null;
  weight?: number;
}

export interface Edge {
  source: string;
  target: string;
  priority?: number;
  guard?: GuardRef | null;
  label?: string | null;
  condition_description?: string | null;
}

export interface BaseNode {
  id: string;
  kind: NodeKind;
  label?: string | null;
  meta?: Record<string, unknown>;
  skippable?: boolean;
  revisitable?: boolean;
  max_attempts?: number;
}

export interface QuestionNode extends BaseNode {
  kind: "Question";
  key: string;
  prompt: string;
  validator?: string | null;
  clarification?: string | null;
  examples?: string[];
  allowed_values?: string[] | null;
  data_type?:
    | "text"
    | "number"
    | "boolean"
    | "date"
    | "email"
    | "phone"
    | "url";
  required?: boolean;
  dependencies?: string[];
  priority?: number;
}

export interface DecisionNode extends BaseNode {
  kind: "Decision";
  decision_type?: "automatic" | "llm_assisted" | "user_choice";
  decision_prompt?: string | null;
}

export interface TerminalNode extends BaseNode {
  kind: "Terminal";
  reason?: string | null;
  success?: boolean;
  next_flow?: string | null;
  handoff_required?: boolean;
}

export interface ActionNode extends BaseNode {
  kind: "Action";
  action_type: string;
  action_config?: Record<string, unknown>;
  output_keys?: string[];
}

export interface SubflowNode extends BaseNode {
  kind: "Subflow";
  flow_ref: string;
  input_mapping?: Record<string, string>;
  output_mapping?: Record<string, string>;
}

export type Node =
  | QuestionNode
  | DecisionNode
  | TerminalNode
  | ActionNode
  | SubflowNode;

export interface PolicyPathSelection {
  lock_threshold?: number;
  allow_switch_before_lock?: boolean;
  confidence_threshold?: number;
  use_llm?: boolean;
}
export interface PolicyConversation {
  allow_clarifications?: boolean;
  max_clarifications?: number;
  allow_skip?: boolean;
  allow_revisit?: boolean;
  conversation_style?: "formal" | "casual" | "technical" | "adaptive";
  use_examples?: boolean;
  maintain_context?: boolean;
}
export interface PolicyValidation {
  strict_validation?: boolean;
  max_validation_attempts?: number;
  validation_strategy?: "immediate" | "deferred" | "batch";
}
export interface Policies {
  path_selection?: PolicyPathSelection | null;
  conversation?: PolicyConversation;
  validation?: PolicyValidation;
}

export interface ValidationRule {
  type: "regex" | "range" | "length" | "custom";
  pattern?: string | null;
  min_value?: number | null;
  max_value?: number | null;
  min_length?: number | null;
  max_length?: number | null;
  function?: string | null;
  error_message?: string | null;
}

export interface FlowMetadata {
  name: string;
  description?: string | null;
  version?: string;
  author?: string | null;
  tags?: string[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Flow {
  schema_version: "v2";
  id: string;
  entry: string;
  metadata?: FlowMetadata | null;
  nodes: Node[];
  edges: Edge[];
  policies?: Policies;
  validations?: Record<string, ValidationRule>;
  context?: Record<string, unknown>;
  subflows?: Record<string, Flow>;
}
```

## Local run (CLI)

Interactively test a flow JSON using the CLI runner. The CLI will normalize legacy files to v2 if needed.

```bash
cd /Users/jessica/me/chatai/backend && source .venv/bin/activate && python -m app.flow_core.cli backend/playground/flow_example.json --llm --model gemini-2.5-flash
```

## Editor notes

- **Unique IDs**: enforce unique node ids and a valid `entry` node.
- **Guard picker**: provide guard templates with argument editors per guard type.
- **Modeling styles**: either explicit linear edges (q1 → q2 → q3) or a `Decision` "chooser" node with `deps_missing` guards to ask next unanswered by `priority`.
- **Strict options (optional)**: if you need fixed choices, you may use `QuestionNode.allowed_values` and equality guards; the example here intentionally avoids them in favor of LLM-assisted routing.
- **Priority & dependencies**: expose in the UI for reordering and gating.
- **Policies**: optional; sensible defaults work.

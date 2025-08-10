## Agent Graph Improvements: Design, Rationale, and Incremental TODO

This document is the starting point for upgrading the agent state graph from a prioritized checklist + single path overlay into a robust, composable flow engine suitable for an AI-powered flow maker (LLM authoring + visual editor).

It captures current behavior, concrete problems and implications, recommended solutions, and a prioritized, incremental TODO checklist with clear acceptance criteria. Treat this as the ignition key: a new LLM can read this file, pick a task, and implement it in isolation.

## Current Behavior (high-level)

- Flat question nodes with fields: `key`, `prompt`, `required`, `priority`, `dependencies`, optional `validate` callback.
- Next step selection = lowest-priority required question with dependencies satisfied and missing answer.
- Paths: one active path selected by an LLM; the effective graph is a shallow merge of global + path by key.
- Extraction: conservative via tools (`UpdateAnswers`, `UnknownAnswer`, `EscalateToHuman`).
- Persistence: `answers` and a `pending_field` key used to bias extraction toward the last asked question.

## Problems and Implications

### 1) Path locking logic incomplete

- Problem: `lock_threshold`, `allow_switch_before_lock`, and vote tracking existed but were unused. Current behavior locks immediately on first LLM choice (no debouncing/hysteresis), which risks premature or unstable path choice.
- Implications: False-positive path selections can derail the conversation. No mechanism for switching when evidence changes.

### 2) No nested subgraphs or transitions

- Problem: The "graph" is a prioritized checklist, not a real directed graph with edges, guards, nested subgraphs, or entry/exit nodes.
- Implications: Cannot model flexible workflows (branching, loops, subflows like identity verification, payment, scheduling). Hard to visualize; limited authoring power.

### 3) Validation hook unused

- Problem: `Question.validate: (value) -> bool` exists but is not invoked when accepting updates or deciding traversal.
- Implications: Invalid values can be stored and advance the flow, leading to bad states and confusing user prompts.

### 4) Dependency model is shallow

- Problem: Dependencies only check presence/non-empty of upstream keys. No value-based predicates, boolean expressions, one-of groups, or cross-field constraints.
- Implications: Cannot express common business logic (e.g., “if product=LED and venue=sports_court then ask wattage”, “ask A or B, not both”, “require either email or phone”). Leads to brittle prompt-only behaviors.

### 5) Prompt-to-key coupling

- Problem: `pending_field` is set by looking up the question via prompt text equality. Although we use the pre-rewrite prompt, this is brittle.
- Implications: Prompt copy edits can desynchronize state; risky localization; hard to reason about.

### 6) Merge order is simplistic

- Problem: Shallow last-wins by key across global+path. No conflict reporting; no per-field merge strategies; equal-priority ordering undefined.
- Implications: Silent overrides, author surprises, difficult debugging and auditing.

### 7) Schema and versioning gaps

- Problem: No stable node IDs, no versioning, no compile-time validation, no visualization metadata.
- Implications: Visual editor cannot provide guarantees; migrations are ad hoc; difficult to diff flows reliably.

### 8) Testing gaps

- Problem: Limited tests (basic checklist). Missing tests for multi-path precedence, path switching/locking, dependency cycles, value-guards, validate hooks, and merge strategies.
- Implications: Changes risky; regressions likely; hard to refactor confidently.

## Recommended Solutions (summary)

1. Introduce a typed Graph IR (intermediate representation)

   - Nodes: question, decision, action/tool, subgraph entry/exit, terminal.
   - Edges: explicit transitions with guard expressions over `answers` and context.
   - Metadata: stable `id`, `key`, `label`, `ui` hints, analytics tags, and `version`.
   - Support subgraph references and scoping for reusability.

2. Traversal engine

   - Maintain `current_node` (not just `pending_field`).
   - Evaluate guards to pick the next edge deterministically; fallbacks on ambiguity.
   - Invoke `validate` (or schema-based validators) before committing updates; on failure, branch to a validation edge.

3. Path selection policy with hysteresis

   - Reintroduce a principled policy: accumulate votes/confidence across turns; lock after threshold; allow switching before lock with hysteresis; expose rationale in logs.
   - Keep default simple, configurable per instance.

4. Rich dependency/guard model

   - Support boolean logic over field values, one-of groups, cross-field constraints.
   - Provide a safe guard expression language (or a predicate registry) with unit tests.

5. Decouple prompts from keys

   - Carry `current_node_id` and `question.key` through the loop and extraction. Never rely on prompt equality.

6. Deterministic, auditable merging

   - Domain-specific merge strategies (override, deep merge, append deps, conflict error) with explicit reports.
   - Deterministic ordering when priorities tie (e.g., by stable node id).

7. Schema + versioning + compiler

   - JSON schema for IR with `version` and semantic validation.
   - Compiler that validates references, detects cycles, compiles guards, and attaches visualization metadata.

8. Comprehensive tests
   - Golden-path tests per flow, guard evaluator tests, merge precedence tests, path policy tests, and visualization rendering smoke tests.

## Incremental TODO Checklist (prioritized)

### P0: Immediate hardening (surgical, low risk)

- [ ] Replace prompt-to-key coupling: set `pending_field` directly from the selected question key and carry a `current_node_key` where applicable.
  - Acceptance: No prompt equality lookups; unit tests cover persistence of key through rewrite.
- [ ] Invoke `Question.validate` before accepting updates; if invalid, do not advance; ask a clarification or follow a validation error branch (temporary: simple retry prompt).
  - Acceptance: Unit tests show invalid values are rejected and flow does not advance.
- [ ] Add value-based dependencies (minimal): allow a `when` predicate on `Question` using a safe evaluator over `answers` (AND only to start).
  - Acceptance: Unit tests for `when` true/false changing applicability.

### P1: Graph IR foundation

- [ ] Define IR schema v0: nodes (question/decision/terminal), edges with `guard`, stable `id`, `key`, `label`, `ui`, `version`.
  - Acceptance: JSON schema with examples; compiler validates and produces internal model.
- [ ] Traversal engine baseline: `current_node`, guard evaluation, deterministic next edge, fallback behavior on ambiguity.
  - Acceptance: Tests for deterministic traversal and guard selection.
- [ ] Subgraph constructs: `SubgraphRef` node type with entry/exit semantics.
  - Acceptance: Tests invoking nested subgraphs and returning to caller.

### P2: Path selection policy

- [ ] Implement vote-based locking with hysteresis: accumulate choices across turns; lock after N confirmations; allow switch before lock; expose conf/logs.
  - Acceptance: Unit tests for early flip-flops, eventual lock, and resistance to single-turn noise.
- [ ] Config surface: per-instance policy knobs; sane defaults.
  - Acceptance: Config parsing + tests.

### P3: Merge and composition

- [ ] Implement deterministic, reported merge: global → industry pack → tenant → instance; per-field strategies configurable; conflict report available for authors.
  - Acceptance: Tests for conflict detection and strategy application.
- [ ] Stable ordering: tie-breaker based on stable node id.
  - Acceptance: Tests confirm consistent ordering across runs.

### P4: Schema, versioning, and visualization

- [ ] Versioned schema evolution plan and migrator utilities (v0 → v1, etc.).
  - Acceptance: Migration test from sample v0 to v1.
- [ ] Visualization metadata: coords, grouping, color hints; export for visual editor.
  - Acceptance: Visual export JSON consumed by a simple viewer.

### P5: Testing and observability

- [ ] Test harness for scripted conversations with snapshot traces of node entries/exits, guard outcomes, and updates.
  - Acceptance: Golden snapshot tests on sample flows.
- [ ] Metrics/logs: structured events for path votes, node transitions, validations.
  - Acceptance: Logs in tests; optional integration hook for analytics.

## Design Details and Guidance

### Path selection with hysteresis (policy sketch)

Inputs per turn: candidate path from LLM (string or None), optional confidence.

State: `path_votes: dict[path, int]`, `active_path`, `path_locked`, config `{lock_threshold, allow_switch_before_lock}`.

Algorithm:

- If `path_locked`: keep `active_path` unless manual override (future work).
- Else:
  - If LLM suggests a path P: increment `path_votes[P]`.
  - If `allow_switch_before_lock` is true and P != current tentative, allow switching tentative path.
  - If `path_votes[P] >= lock_threshold`: set `active_path=P`, `path_locked=True`.
  - Optionally decay votes for non-selected paths to add hysteresis.

Note: We recently removed unused votes/threshold code; this policy would reintroduce it with real behavior and tests.

### Nested subgraphs (IR sketch)

Example IR snippet:

```json
{
  "version": "v1",
  "id": "flow.sales",
  "nodes": [
    { "id": "n.start", "type": "decision", "label": "Start" },
    {
      "id": "q.intent",
      "type": "question",
      "key": "intention",
      "prompt": "What do you need?"
    },
    { "id": "sg.led", "type": "subgraph", "ref": "subgraph.led_path" },
    { "id": "n.done", "type": "terminal", "label": "Done" }
  ],
  "edges": [
    { "from": "n.start", "to": "q.intent" },
    {
      "from": "q.intent",
      "to": "sg.led",
      "guard": "answers.intention == 'buy_led'"
    },
    { "from": "q.intent", "to": "n.done", "guard": "else" }
  ],
  "subgraphs": {
    "subgraph.led_path": {
      "entry": "q.court_size",
      "nodes": [
        {
          "id": "q.court_size",
          "type": "question",
          "key": "court_size",
          "prompt": "Court size?"
        },
        {
          "id": "q.wattage",
          "type": "question",
          "key": "wattage",
          "prompt": "Desired wattage?"
        }
      ],
      "edges": [
        { "from": "q.court_size", "to": "q.wattage" },
        { "from": "q.wattage", "to": "__exit__" }
      ]
    }
  }
}
```

Traversal keeps a call stack of subgraphs; `__exit__` returns to caller edge target.

### Validation hook usage

- Purpose: ensure values are acceptable before committing and moving forward.
- Behavior: after extraction proposes updates, for each updated key resolve its node, run its validation (or schema-based validator). If invalid:
  - Do not commit; keep focus on the same question node.
  - Use a validation-error prompt or edge to clarify/retry.
  - Log validation failures for observability.

### Dependency and guard model

- From presence-only to value-aware:
  - Add `when` (boolean expression) to nodes; compute applicability from `answers`.
  - Add one-of constraints at flow level: `oneOf: [["email"], ["phone"]]`.
  - Add cross-field constraints as named predicates (e.g., `contact_info_present`).
  - Guard language: restricted expressions over a safe subset (no eval). Consider a tiny interpreter or a compiled predicate registry.

### Merge strategies and libraries

Options:

- Domain-specific merge we implement: predictable, explicit strategies per field (`override`, `deep-merge-deps`, `concat`, `error`), with a conflict report artifact.
- Libraries:
  - `jsonschema` for schema/validation.
  - `jsonmerge` or `deepmerge` for structural merging (general-purpose; may not fit domain conflict semantics).
  - `jsonpatch`/`jsondiff` for diffs and audit trails.

Recommendation: implement a small domain merge layer for nodes/edges (clear semantics) and use `jsonschema` for validation. Avoid overfitting to generic merge tools where intent matters (prompts, deps, guards).

## Near-Term Implementation Notes

- Keep current extraction flow but ensure we carry `question.key`/`node.id` through, not prompt text.
- Add defensive compile-time checks: duplicate keys, unreachable nodes, missing references, cycles (unless explicitly allowed).
- Introduce feature flags to roll out IR traversal per agent instance.

## Test Plan (high-level)

- Checklist traversal remains deterministic after key-based carry.
- Validation hook prevents invalid progression; shows retry prompt.
- Guards enable/disable questions based on values; snapshot tests of applicability.
- Path policy hysteresis: early flip-flops do not lock; consistent multi-turn evidence locks.
- Merge precedence: global vs path vs tenant vs instance; conflicts reported; ordering deterministic.
- Subgraph traversal: call/return semantics correct under nesting; stack unwinds properly on completion.

## Migration Strategy

1. P0 changes are backward-compatible; no config migrations required.
2. Introduce IR alongside existing model; provide a converter for current checklist configs to IR v0.
3. Add dual-mode traversal behind a flag; run shadow evaluations in tests.
4. Migrate flows incrementally; provide tooling to diff and validate.

## Open Questions

- Should guard language be expression-based or registry-based? Start with registry for safety; layer expressions later.
- Confidence signals from LLM path selection: do we standardize a tool signature to include confidence? If not available, rely on votes only.
- How to expose merge conflict reports to authors in the visual editor (inline warnings vs. pre-publish checks)?

## Appendix: Minimal IR JSON Schema (draft)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/agent-flow.schema.json",
  "title": "Agent Flow IR",
  "type": "object",
  "required": ["version", "id", "nodes", "edges"],
  "properties": {
    "version": { "type": "string" },
    "id": { "type": "string" },
    "nodes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "type"],
        "properties": {
          "id": { "type": "string" },
          "type": {
            "enum": ["question", "decision", "action", "subgraph", "terminal"]
          },
          "key": { "type": "string" },
          "prompt": { "type": "string" },
          "ui": { "type": "object" }
        }
      }
    },
    "edges": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["from", "to"],
        "properties": {
          "from": { "type": "string" },
          "to": { "type": "string" },
          "guard": { "type": ["string", "null"], "default": null }
        }
      }
    },
    "subgraphs": { "type": "object" }
  }
}
```

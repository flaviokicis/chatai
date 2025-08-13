export type NodeKind = "Question" | "Decision" | "Terminal" | "Action" | "Subflow" | string;

export interface FlowNodeSummaryBase {
  id: string;
  kind: NodeKind;
  label?: string | null;
  skippable?: boolean;
  revisitable?: boolean;
  max_attempts?: number;
}

export interface QuestionNodeSummary extends FlowNodeSummaryBase {
  kind: "Question";
  key?: string;
  prompt?: string;
  validator?: string | null;
  clarification?: string | null;
  examples?: string[];
  allowed_values?: string[] | null;
  data_type?: "text" | "number" | "boolean" | "date" | "email" | "phone" | "url";
  required?: boolean;
  dependencies?: string[];
  priority?: number;
}

export interface DecisionNodeSummary extends FlowNodeSummaryBase {
  kind: "Decision";
  decision_type?: "automatic" | "llm_assisted" | "user_choice";
  decision_prompt?: string | null;
}

export interface TerminalNodeSummary extends FlowNodeSummaryBase {
  kind: "Terminal";
  reason?: string | null;
  success?: boolean;
  next_flow?: string | null;
  handoff_required?: boolean;
}

export interface ActionNodeSummary extends FlowNodeSummaryBase {
  kind: "Action";
  action_type?: string;
  action_config?: Record<string, unknown>;
  output_keys?: string[];
}

export interface SubflowNodeSummary extends FlowNodeSummaryBase {
  kind: "Subflow";
  flow_ref?: string;
  input_mapping?: Record<string, string>;
  output_mapping?: Record<string, string>;
}

export type FlowNodeSummary =
  | QuestionNodeSummary
  | DecisionNodeSummary
  | TerminalNodeSummary
  | ActionNodeSummary
  | SubflowNodeSummary;

export interface FlowEdgeSummary {
  source: string;
  target: string;
  priority?: number;
  label?: string | null;
  condition_description?: string | null;
}

// Minimal shape returned by backend /flows/example/compiled
export interface CompiledFlow {
  id: string;
  entry: string;
  nodes: Record<string, FlowNodeSummary>;
  edges_from: Record<string, FlowEdgeSummary[]>;
  subflows?: Record<string, CompiledFlow>;
}

export type PositionedNode = FlowNodeSummary & {
  isEntry: boolean;
  outgoing: FlowEdgeSummary[];
};

export interface FlowLayoutColumn {
  columnIndex: number;
  nodes: PositionedNode[];
}

export interface EdgeSegment {
  from: { x: number; y: number };
  to: { x: number; y: number };
}

export interface MeasuredNodeRect {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

// Utility types for rendering/highlighting
export type EdgeKey = `${string}->${string}`;
export interface EdgeStyle {
  color?: string;
  width?: number;
  opacity?: number;
  dashed?: boolean;
}



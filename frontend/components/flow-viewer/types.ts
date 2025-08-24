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

export interface FlowUILabels {
  global_section_label?: string;
  branch_section_prefix?: string;
  terminal_completion_label?: string;
  locale?: string;
}

export interface FlowMetadata {
  name: string;
  description?: string | null;
  version?: string;
  author?: string | null;
  tags?: string[];
  created_at?: string | null;
  updated_at?: string | null;
  ui_labels?: FlowUILabels;
}

// Minimal shape returned by backend /flows/example/compiled
export interface CompiledFlow {
  id: string;
  entry: string;
  nodes: Record<string, FlowNodeSummary>;
  edges_from: Record<string, FlowEdgeSummary[]>;
  subflows?: Record<string, CompiledFlow>;
  metadata?: FlowMetadata | null;
}

export type PositionedNode = FlowNodeSummary & {
  isEntry: boolean;
  outgoing: FlowEdgeSummary[];
};

export interface FlowLayoutColumn {
  columnIndex: number;
  nodes: PositionedNode[];
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
// Reserved for future edge styling extensions



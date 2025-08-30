"use client";

import { GitBranch } from "lucide-react";
import { BaseFlowNode } from "./BaseFlowNode";
import type { DecisionNodeSummary } from "../types";

interface DecisionNodeProps {
  data: DecisionNodeSummary & {
    label?: string;
    isEntry?: boolean;
  };
}

export function DecisionNode({ data }: DecisionNodeProps) {
  return (
    <BaseFlowNode
      data={data}
      icon={<GitBranch className="w-4 h-4 text-yellow-600" />}
      bgColor="bg-yellow-50"
      borderColor="border-yellow-200"
      textColor="text-yellow-800"
      kindLabel="Decisão"
    />
  );
}

"use client";

import { Zap } from "lucide-react";
import { BaseFlowNode } from "./BaseFlowNode";
import type { ActionNodeSummary } from "../types";

interface ActionNodeProps {
  data: ActionNodeSummary & {
    label?: string;
    isEntry?: boolean;
  };
}

export function ActionNode({ data }: ActionNodeProps) {
  return (
    <BaseFlowNode
      data={data}
      icon={<Zap className="w-4 h-4 text-purple-600" />}
      bgColor="bg-purple-50"
      borderColor="border-purple-200"
      textColor="text-purple-800"
      kindLabel="Ação"
    />
  );
}

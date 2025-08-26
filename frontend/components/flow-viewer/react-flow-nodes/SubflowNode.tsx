"use client";

import { Workflow, ExternalLink } from "lucide-react";
import { BaseFlowNode } from "./BaseFlowNode";
import type { SubflowNodeSummary } from "../types";

interface SubflowNodeProps {
  data: SubflowNodeSummary & {
    label?: string;
    isEntry?: boolean;
    onSubflowClick?: (subflowId: string) => void;
  };
}

export function SubflowNode({ data }: SubflowNodeProps) {
  const handleSubflowClick = () => {
    if (data.flow_ref && data.onSubflowClick) {
      data.onSubflowClick(data.flow_ref);
    }
  };

  return (
    <div className="relative">
      <BaseFlowNode
        data={data}
        icon={<Workflow className="w-4 h-4 text-indigo-600" />}
        bgColor="bg-indigo-50"
        borderColor="border-indigo-200"
        textColor="text-indigo-800"
        kindLabel="Subfluxo"
      />
      
      {/* Overlay button for subflow navigation */}
      {data.flow_ref && (
        <button
          onClick={handleSubflowClick}
          className="absolute top-2 right-2 p-1 bg-indigo-100 hover:bg-indigo-200 rounded-full transition-colors"
          title={`Navegar para ${data.flow_ref}`}
        >
          <ExternalLink className="w-3 h-3 text-indigo-600" />
        </button>
      )}
    </div>
  );
}

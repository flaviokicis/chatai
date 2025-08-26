"use client";

import { Square, CheckCircle } from "lucide-react";
import { BaseFlowNode } from "./BaseFlowNode";
import type { TerminalNodeSummary } from "../types";

interface TerminalNodeProps {
  data: TerminalNodeSummary & {
    label?: string;
    isEntry?: boolean;
  };
}

export function TerminalNode({ data }: TerminalNodeProps) {
  const isSuccess = data.success ?? true;
  
  return (
    <BaseFlowNode
      data={data}
      icon={
        isSuccess 
          ? <CheckCircle className="w-4 h-4 text-green-600" />
          : <Square className="w-4 h-4 text-red-600" />
      }
      bgColor={isSuccess ? "bg-green-50" : "bg-red-50"}
      borderColor={isSuccess ? "border-green-200" : "border-red-200"}
      textColor={isSuccess ? "text-green-800" : "text-red-800"}
      kindLabel="Finalização"
    />
  );
}

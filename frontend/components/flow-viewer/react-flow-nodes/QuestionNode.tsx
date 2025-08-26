"use client";

import { MessageCircle } from "lucide-react";
import { BaseFlowNode } from "./BaseFlowNode";
import type { QuestionNodeSummary } from "../types";

interface QuestionNodeProps {
  data: QuestionNodeSummary & {
    label?: string;
    isEntry?: boolean;
  };
}

export function QuestionNode({ data }: QuestionNodeProps) {
  return (
    <BaseFlowNode
      data={data}
      icon={<MessageCircle className="w-4 h-4 text-blue-600" />}
      bgColor="bg-blue-50"
      borderColor="border-blue-200"
      textColor="text-blue-800"
      kindLabel="Pergunta"
    />
  );
}

"use client";

import { Handle, Position } from "@xyflow/react";
import { useState } from "react";
import { ChevronDown, ChevronUp, Info } from "lucide-react";
import type { FlowNodeSummary } from "../types";

interface BaseFlowNodeProps {
  data: FlowNodeSummary & {
    label?: string;
    isEntry?: boolean;
  };
  icon: React.ReactNode;
  bgColor: string;
  borderColor: string;
  textColor: string;
  kindLabel: string;
}

export function BaseFlowNode({
  data,
  icon,
  bgColor,
  borderColor,
  textColor,
  kindLabel,
}: BaseFlowNodeProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  const title = data.label || data.id;
  const hasDetails = Boolean(
    (data as any).prompt ||
    (data as any).decision_prompt ||
    (data as any).reason ||
    (data as any).action_type
  );

  return (
    <div className="relative">
      {/* Input handle */}
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: '#555' }}
        isConnectable={false}
      />

      <div
        className={`min-w-[250px] max-w-[400px] rounded-lg border-2 ${bgColor} ${borderColor} shadow-sm hover:shadow-md transition-all duration-200`}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 pb-3">
          <div className="flex items-center gap-2">
            {icon}
            <span className={`text-xs font-medium px-2 py-1 rounded ${textColor} bg-white/20`}>
              {kindLabel}
            </span>
          </div>
          {data.isEntry && (
            <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded font-medium">
              Início
            </span>
          )}
        </div>

        {/* Title */}
        <div className="px-4 pb-3">
          <div className="font-medium text-base text-gray-900 leading-tight">
            {title}
          </div>
        </div>

        {/* Node ID */}
        <div className="px-4 pb-2">
          <div className="text-xs text-gray-500 font-mono">
            {data.id}
          </div>
        </div>

        {/* Expand/Details buttons */}
        {hasDetails && (
          <div className="px-4 pb-4 flex gap-2">
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="flex items-center gap-1 text-xs bg-white/30 hover:bg-white/50 px-2 py-1 rounded transition-colors"
            >
              {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              {isExpanded ? 'Menos' : 'Mais'}
            </button>
            <button
              onClick={() => setShowDetails(true)}
              className="flex items-center gap-1 text-xs bg-blue-100 hover:bg-blue-200 text-blue-800 px-2 py-1 rounded transition-colors"
            >
              <Info className="w-3 h-3" />
              Detalhes
            </button>
          </div>
        )}

        {/* Expanded content */}
        {isExpanded && hasDetails && (
          <div className="px-4 pb-4 border-t bg-white/10">
            <div className="pt-2 text-xs text-gray-700">
              {(data as any).prompt && (
                <div>
                  <div className="font-medium mb-1">Pergunta:</div>
                  <div className="text-gray-600">{(data as any).prompt}</div>
                </div>
              )}
              {(data as any).decision_prompt && (
                <div>
                  <div className="font-medium mb-1">Lógica de decisão:</div>
                  <div className="text-gray-600">{(data as any).decision_prompt}</div>
                </div>
              )}
              {(data as any).reason && (
                <div>
                  <div className="font-medium mb-1">Motivo:</div>
                  <div className="text-gray-600">{(data as any).reason}</div>
                </div>
              )}
              {(data as any).action_type && (
                <div>
                  <div className="font-medium mb-1">Tipo de ação:</div>
                  <div className="text-gray-600">{(data as any).action_type}</div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Output handle */}
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: '#555' }}
        isConnectable={false}
      />

      {/* Details modal */}
      {showDetails && (
        <div 
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={() => setShowDetails(false)}
        >
          <div 
            className="bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                {icon}
                <h3 className="font-medium">{kindLabel}: {title}</h3>
              </div>
              <button 
                onClick={() => setShowDetails(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                ×
              </button>
            </div>
            
            <div className="space-y-3 text-sm">
              <div>
                <span className="font-medium">ID:</span> <span className="font-mono text-xs">{data.id}</span>
              </div>
              
              {(data as any).prompt && (
                <div>
                  <div className="font-medium mb-1">Pergunta que será feita ao usuário:</div>
                  <div className="bg-blue-50 p-3 rounded text-blue-900">
                    {(data as any).prompt}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    Nota: A pergunta pode ser reformulada automaticamente para soar mais natural na conversa.
                  </div>
                </div>
              )}
              
              {(data as any).decision_prompt && (
                <div>
                  <div className="font-medium mb-1">Como a decisão é tomada:</div>
                  <div className="bg-yellow-50 p-3 rounded text-yellow-900">
                    {(data as any).decision_prompt}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    Esta lógica determina automaticamente qual será o próximo passo.
                  </div>
                </div>
              )}
              
              {(data as any).reason && (
                <div>
                  <div className="font-medium mb-1">O que acontece aqui:</div>
                  <div className="bg-gray-50 p-3 rounded text-gray-900">
                    {(data as any).reason}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    Este é um ponto final do fluxo de conversa.
                  </div>
                </div>
              )}
              
              {(data as any).action_type && (
                <div>
                  <div className="font-medium mb-1">Ação executada:</div>
                  <div className="bg-green-50 p-3 rounded text-green-900">
                    {(data as any).action_type}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    Esta ação é executada automaticamente pelo sistema.
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

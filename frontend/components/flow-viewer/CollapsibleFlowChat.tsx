"use client";

import { useState } from "react";
import { ChevronUp, ChevronDown, MessageSquare } from "lucide-react";
import { FlowEditorChat } from "./FlowEditorChat";

interface Props {
  flowId: string;
  onFlowModified?: () => void;
  simplifiedViewEnabled?: boolean;
  activePath?: string | null;
}

export function CollapsibleFlowChat({ 
  flowId, 
  onFlowModified, 
  simplifiedViewEnabled = false, 
  activePath = null 
}: Props) {
  const [isExpanded, setIsExpanded] = useState(false);

  const toggleChat = () => {
    setIsExpanded(!isExpanded);
  };

  return (
    <div className="fixed bottom-4 right-4 z-50">
      {/* Chat container */}
      <div 
        className={`bg-card border rounded-xl shadow-lg transition-all duration-300 ease-in-out ${
          isExpanded 
            ? 'w-[480px] h-[700px] opacity-100 scale-100' 
            : 'w-0 h-0 opacity-0 scale-95 overflow-hidden'
        }`}
      >
        {isExpanded && (
          <div className="h-full">
            <FlowEditorChat 
              flowId={flowId} 
              onFlowModified={onFlowModified} 
              simplifiedViewEnabled={simplifiedViewEnabled}
              activePath={activePath}
            />
          </div>
        )}
      </div>
      
      {/* Chat tab/button */}
      <div 
        className={`bg-card border rounded-t-xl shadow-lg cursor-pointer hover:bg-card/90 transition-colors ${
          isExpanded ? 'rounded-b-none border-b-0' : 'rounded-xl'
        }`}
        onClick={toggleChat}
      >
        <div className="px-4 py-3 flex items-center gap-2 text-sm font-medium">
          <MessageSquare className="h-4 w-4" />
          <span>Editor do fluxo</span>
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 ml-auto" />
          ) : (
            <ChevronUp className="h-4 w-4 ml-auto" />
          )}
        </div>
      </div>
    </div>
  );
}

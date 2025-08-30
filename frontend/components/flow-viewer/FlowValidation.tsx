"use client";

import { useState } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, ChevronDown, ChevronRight } from "lucide-react";

interface ValidationMessage {
  type: 'error' | 'warning';
  message: string;
  nodeId?: string;
}

interface Props {
  validationResult: string | null;
  className?: string;
}

export function FlowValidation({ validationResult, className = "" }: Props) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!validationResult) {
    return null;
  }

  // Parse validation result to extract errors and warnings
  const parseValidationResult = (result: string): { 
    status: 'valid' | 'warnings' | 'errors';
    messages: ValidationMessage[];
  } => {
    if (result.includes("Flow validation passed")) {
      return { status: 'valid', messages: [] };
    }

    const messages: ValidationMessage[] = [];
    const lines = result.split('\n').filter(line => line.trim());

    for (const line of lines) {
      if (line.includes('validation failed') || line.includes('Failed to validate')) {
        // Extract error messages
        const errorMatch = line.match(/- (.+)/);
        if (errorMatch) {
          messages.push({
            type: 'error',
            message: errorMatch[1]
          });
        }
      } else if (line.includes('warnings')) {
        // Extract warning messages  
        const warningMatch = line.match(/- (.+)/);
        if (warningMatch) {
          messages.push({
            type: 'warning', 
            message: warningMatch[1]
          });
        }
      }
    }

    const hasErrors = messages.some(m => m.type === 'error') || result.includes('validation failed');
    return {
      status: hasErrors ? 'errors' : messages.length > 0 ? 'warnings' : 'valid',
      messages
    };
  };

  const { status, messages } = parseValidationResult(validationResult);

  const getStatusIcon = () => {
    switch (status) {
      case 'valid':
        return <CheckCircle2 className="h-4 w-4 text-green-500" />;
      case 'warnings':
        return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
      case 'errors':
        return <AlertCircle className="h-4 w-4 text-red-500" />;
    }
  };

  const getStatusText = () => {
    switch (status) {
      case 'valid':
        return "Fluxo válido";
      case 'warnings':
        return `${messages.length} aviso${messages.length !== 1 ? 's' : ''}`;
      case 'errors':
        return `${messages.length} erro${messages.length !== 1 ? 's' : ''}`;
    }
  };

  const getStatusColor = () => {
    switch (status) {
      case 'valid':
        return "text-green-600 bg-green-50 border-green-200";
      case 'warnings':
        return "text-yellow-600 bg-yellow-50 border-yellow-200";
      case 'errors':
        return "text-red-600 bg-red-50 border-red-200";
    }
  };

  return (
    <div className={`border rounded-lg ${getStatusColor()} ${className}`}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-3 flex items-center justify-between text-sm font-medium hover:opacity-80"
      >
        <div className="flex items-center gap-2">
          {getStatusIcon()}
          <span>{getStatusText()}</span>
        </div>
        {messages.length > 0 && (
          isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />
        )}
      </button>
      
      {isExpanded && messages.length > 0 && (
        <div className="border-t px-3 pb-3 space-y-2">
          {messages.map((message, index) => (
            <div key={index} className="flex items-start gap-2 text-xs">
              {message.type === 'error' ? (
                <AlertCircle className="h-3 w-3 text-red-500 mt-0.5 flex-shrink-0" />
              ) : (
                <AlertTriangle className="h-3 w-3 text-yellow-500 mt-0.5 flex-shrink-0" />
              )}
              <span className="leading-tight">{message.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import type { FlowChatMessage } from "@/lib/api-client";
import { api } from "@/lib/api-client";
import { toast } from "sonner";
import { AlertCircle, Loader2, RefreshCw, Zap } from "lucide-react";
import { FlowValidation } from "./FlowValidation";
import { FlowHistory } from "./FlowHistory";

interface Props {
  flowId: string;
  onFlowModified?: () => void;
}

export function FlowEditorChat({ flowId, onFlowModified }: Props) {
  const [messages, setMessages] = useState<Array<{ role: "user" | "assistant"; text: string; hasError?: boolean }>>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastValidationResult, setLastValidationResult] = useState<string | null>(null);

  useEffect(() => {
    setLoadingMessages(true);
    setError(null);
    
    api.flowChat
      .list(flowId)
      .then((msgs) => {
        setMessages(msgs.map((m: FlowChatMessage) => ({ role: m.role, text: m.content })));
        setError(null);
      })
      .catch((err) => {
        console.error("Failed to load chat messages:", err);
        setError("Falha ao carregar mensagens do chat");
        // Fallback to default messages
        setMessages([
          {
            role: "assistant",
            text: "Oi! Me diga como você quer ajustar este fluxo e eu preparo as mudanças.",
          },
          {
            role: "assistant",
            text: "Cole uma conversa de WhatsApp inteira para criar ou modificar o fluxo de conversa.",
          },
        ]);
      })
      .finally(() => {
        setLoadingMessages(false);
      });
  }, [flowId]);

  // Helper function to detect if assistant response indicates a flow modification
  function detectFlowModification(text: string): boolean {
    const modificationIndicators = [
      'Successfully set complete flow definition',
      'Added node',
      'Updated node',
      'Deleted node', 
      'Added edge',
      'Updated edge',
      'Deleted edge',
      'Flow is valid and ready to use'
    ];
    return modificationIndicators.some(indicator => text.includes(indicator));
  }

  // Helper function to detect validation results
  function extractValidationResult(text: string): string | null {
    if (text.includes('Flow validation passed') || 
        text.includes('Flow validation failed') || 
        text.includes('Flow is valid with warnings')) {
      return text;
    }
    return null;
  }

  // Quick validation function
  const triggerValidation = async () => {
    const validationText = "Valide este fluxo";
    setIsSending(true);
    setInput(validationText);
    
    setMessages((m) => [...m, { role: "user", text: validationText }]);
    setInput("");
    setIsSending(false);
    setIsLoading(true);
    
    try {
      const responses = await api.flowChat.send(flowId, validationText);
      const newMessages = responses.map((r) => ({ 
        role: r.role as "user" | "assistant", 
        text: r.content 
      }));
      
      setMessages((m) => [...m, ...newMessages]);
      
      // Extract validation result
      const validationResult = newMessages.find(msg => 
        msg.role === "assistant" && extractValidationResult(msg.text)
      );
      
      if (validationResult) {
        setLastValidationResult(validationResult.text);
      }
      
    } catch (err: unknown) {
      console.error("Failed to validate flow:", err);
      toast.error("Falha ao validar fluxo");
    } finally {
      setIsLoading(false);
    }
  };

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    
    setIsSending(true);
    setError(null);
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setIsSending(false); // Message sent, button back to normal
    setIsLoading(true); // Start processing
    
    try {
      const responses = await api.flowChat.send(flowId, text);
      const newMessages = responses.map((r) => ({ 
        role: r.role as "user" | "assistant", 
        text: r.content 
      }));
      
      setMessages((m) => [...m, ...newMessages]);
      
      // Check if any response indicates a flow modification
      const hasModification = newMessages.some(msg => 
        msg.role === "assistant" && detectFlowModification(msg.text)
      );
      
      // Check for validation results
      const validationResult = newMessages.find(msg => 
        msg.role === "assistant" && extractValidationResult(msg.text)
      );
      
      if (validationResult) {
        setLastValidationResult(validationResult.text);
      }
      
      if (hasModification) {
        toast.success("Fluxo modificado com sucesso");
        onFlowModified?.();
      }
      
      setError(null);
    } catch (err: unknown) {
      console.error("Failed to send message:", err);
      
      let errorMessage = "Falha ao enviar mensagem";
      if (err.status === 400) {
        errorMessage = "Mensagem inválida - verifique o formato";
      } else if (err.status === 500) {
        errorMessage = "Erro interno do servidor - tente novamente";
      } else if (err.status >= 500) {
        errorMessage = "Servidor indisponível - tente novamente em alguns minutos";
      }
      
      setError(errorMessage);
      setMessages((m) => [...m, { 
        role: "assistant", 
        text: `❌ ${errorMessage}`, 
        hasError: true 
      }]);
      
      toast.error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  }

  const retryLastMessage = () => {
    if (messages.length >= 2) {
      const lastUserMessage = [...messages].reverse().find(m => m.role === "user");
      if (lastUserMessage) {
        setInput(lastUserMessage.text);
        // Remove the last error message
        setMessages(prev => prev.filter((_, i) => i !== prev.length - 1));
      }
    }
  };

  return (
    <div className="rounded-xl border bg-card text-card-foreground shadow-sm flex flex-col h-[420px] sm:h-[480px]">
      <div className="p-3 border-b text-sm font-medium flex items-center justify-between">
        <span>Editor do fluxo (beta)</span>
        <div className="flex items-center gap-2">
          <button
            onClick={triggerValidation}
            disabled={isSending || isLoading || loadingMessages}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-secondary hover:bg-secondary/80 disabled:opacity-50"
            title="Validar fluxo"
          >
            <Zap className="h-3 w-3" />
            Validar
          </button>
          {(isSending || isLoading) && <Loader2 className="h-4 w-4 animate-spin" />}
        </div>
      </div>
      <div className="px-3 pt-2 space-y-2">
        {lastValidationResult && (
          <FlowValidation validationResult={lastValidationResult} />
        )}
        <FlowHistory 
          flowId={flowId} 
          onFlowRestored={onFlowModified}
        />
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {loadingMessages ? (
          <div className="h-full flex items-center justify-center">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Carregando mensagens...
            </div>
          </div>
        ) : error && messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center space-y-3 px-4">
            <AlertCircle className="h-8 w-8 text-destructive" />
            <div className="text-sm text-muted-foreground">
              <div className="mb-2">{error}</div>
              <button 
                onClick={() => window.location.reload()} 
                className="text-xs text-primary hover:underline flex items-center gap-1"
              >
                <RefreshCw className="h-3 w-3" />
                Tentar novamente
              </button>
            </div>
          </div>
        ) : messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center space-y-3 px-4">
            <div className="text-sm text-muted-foreground max-w-xs">
              <div className="mb-2">Converse neste chat para fazer edições no fluxo</div>
              <div className="text-xs opacity-75">Ou cole uma conversa inteira que serve de exemplo</div>
            </div>
          </div>
        ) : (
          <>
            {messages.map((m, i) => (
              <div key={i} className={`max-w-[85%] rounded-2xl px-3 py-2 ${
                m.hasError 
                  ? "bg-destructive/10 border border-destructive/20" 
                  : m.role === "assistant" 
                    ? "bg-muted" 
                    : "bg-primary text-primary-foreground ml-auto"
              }`}>
                <div className="text-sm leading-relaxed whitespace-pre-wrap flex items-start gap-2">
                  {m.hasError && <AlertCircle className="h-4 w-4 text-destructive mt-0.5 flex-shrink-0" />}
                  <span className={m.hasError ? "text-destructive" : ""}>{m.text}</span>
                </div>
                {m.hasError && (
                  <button 
                    onClick={retryLastMessage}
                    className="text-xs text-destructive hover:underline mt-1 flex items-center gap-1"
                  >
                    <RefreshCw className="h-3 w-3" />
                    Tentar novamente
                  </button>
                )}
              </div>
            ))}
            {isLoading && (
              <div className="max-w-[85%] rounded-2xl px-3 py-2 bg-muted">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Processando...
                </div>
              </div>
            )}
          </>
        )}
      </div>
      <form onSubmit={onSubmit} className="p-3 border-t flex items-center gap-2">
        <input
          className="flex-1 min-w-0 rounded-lg border bg-background px-3 py-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          placeholder="Conte rapidamente o que você quer mudar neste fluxo…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isSending || isLoading || loadingMessages}
        />
        <button 
          type="submit" 
          disabled={isSending || isLoading || loadingMessages || !input.trim()}
          className="rounded-lg bg-primary text-primary-foreground px-3 py-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center gap-2 min-w-[90px] flex-shrink-0 justify-center"
        >
          {isSending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Enviando
            </>
          ) : (
            "Enviar"
          )}
        </button>
      </form>
    </div>
  );
}



"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type FlowVersion } from "@/lib/api-client";
import { toast } from "sonner";
import { 
  History, 
  Loader2, 
  RotateCcw, 
  ChevronDown, 
  ChevronRight,
  Clock,
  User
} from "lucide-react";

interface Props {
  flowId: string;
  onFlowRestored?: () => void;
  className?: string;
}

export function FlowHistory({ flowId, onFlowRestored, className = "" }: Props) {
  const [isExpanded, setIsExpanded] = useState(false);
  const queryClient = useQueryClient();

  const { data: versions, isLoading } = useQuery({
    queryKey: ["flowVersions", flowId],
    queryFn: () => api.flows.getVersions(flowId),
    enabled: isExpanded, // Only fetch when expanded
    staleTime: 1000 * 60 * 5, // 5 minutes
  });

  const restoreMutation = useMutation({
    mutationFn: (versionNumber: number) => api.flows.restoreVersion(flowId, versionNumber),
    onSuccess: (data) => {
      toast.success(`Fluxo restaurado para versão ${data.current_version - 1}`);
      // Invalidate queries to refresh data
      queryClient.invalidateQueries({ queryKey: ["compiledFlow", flowId] });
      queryClient.invalidateQueries({ queryKey: ["flowVersions", flowId] });
      onFlowRestored?.();
    },
    onError: (error: any) => {
      console.error("Failed to restore version:", error);
      toast.error("Falha ao restaurar versão");
    },
  });

  const formatTimeAgo = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return "agora";
    if (diffMins < 60) return `${diffMins}m atrás`;
    if (diffHours < 24) return `${diffHours}h atrás`;
    if (diffDays < 30) return `${diffDays}d atrás`;
    return date.toLocaleDateString('pt-BR');
  };

  const handleRestore = (versionNumber: number) => {
    if (window.confirm(`Tem certeza que deseja restaurar o fluxo para a versão ${versionNumber}? Esta ação não pode ser desfeita.`)) {
      restoreMutation.mutate(versionNumber);
    }
  };

  return (
    <div className={`border rounded-lg bg-card ${className}`}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-3 flex items-center justify-between text-sm font-medium hover:bg-muted/50"
      >
        <div className="flex items-center gap-2">
          <History className="h-4 w-4" />
          <span>Histórico de alterações</span>
          {versions && versions.length > 0 && (
            <span className="text-xs text-muted-foreground">({versions.length})</span>
          )}
        </div>
        {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
      </button>
      
      {isExpanded && (
        <div className="border-t max-h-60 overflow-y-auto">
          {isLoading ? (
            <div className="p-4 flex items-center justify-center">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Carregando histórico...
              </div>
            </div>
          ) : !versions || versions.length === 0 ? (
            <div className="p-4 text-center text-sm text-muted-foreground">
              Nenhuma alteração anterior encontrada
            </div>
          ) : (
            <div className="space-y-0">
              {versions.map((version, index) => (
                <div 
                  key={version.id} 
                  className="p-3 border-b last:border-b-0 hover:bg-muted/30 transition-colors"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                        <Clock className="h-3 w-3" />
                        <span>Versão {version.version_number}</span>
                        <span>•</span>
                        <span>{formatTimeAgo(version.created_at)}</span>
                        {version.created_by && (
                          <>
                            <span>•</span>
                            <User className="h-3 w-3" />
                            <span>{version.created_by}</span>
                          </>
                        )}
                      </div>
                      <div className="text-sm">
                        {version.change_description || "Alteração sem descrição"}
                      </div>
                    </div>
                    <button
                      onClick={() => handleRestore(version.version_number)}
                      disabled={restoreMutation.isPending || index === 0}
                      className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-secondary hover:bg-secondary/80 disabled:opacity-50 disabled:cursor-not-allowed"
                      title={index === 0 ? "Versão atual" : "Restaurar esta versão"}
                    >
                      <RotateCcw className="h-3 w-3" />
                      {index === 0 ? "Atual" : "Restaurar"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

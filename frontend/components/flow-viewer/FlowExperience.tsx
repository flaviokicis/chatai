"use client";

import { useEffect, useMemo, useState } from "react";
import type { CompiledFlow, FlowEdgeSummary } from "./types";
import { JourneyPreview, type JourneyStep } from "./JourneyPreview";
import { ReactFlowViewer } from "./ReactFlowViewer";
import { pickLabel, sortedOutgoing } from "./helpers";

type BranchOption = { targetId: string; label: string };

function findFirstBranchDecision(flow: CompiledFlow): string | null {
  const queue: string[] = [flow.entry];
  const visited = new Set<string>();
  while (queue.length) {
    const id = queue.shift()!;
    if (visited.has(id)) continue;
    visited.add(id);
    const node = flow.nodes[id];
    if (!node) continue;
    const outs = flow.edges_from[id] ?? [];
    if (node.kind === "Decision" && outs.length > 1) return id;
    outs.forEach((e) => queue.push(e.target));
  }
  return null;
}

function computePath(flow: CompiledFlow, branchSelection: Record<string, string>, maxSteps = 200): string[] {
  const nodes: string[] = [];
  let current = flow.entry;
  let steps = 0;
  const visited = new Set<string>();
  while (current && steps < maxSteps) {
    nodes.push(current);
    visited.add(current);
    const outs = sortedOutgoing(flow, current);
    if (outs.length === 0) break;
    let chosen: FlowEdgeSummary | undefined;
    if (flow.nodes[current]?.kind === "Decision" && outs.length > 1) {
      const preferredTarget = branchSelection[current];
      chosen = outs.find((e) => e.target === preferredTarget) ?? outs[0];
    } else {
      chosen = outs[0];
    }
    if (!chosen) break;
    current = chosen.target;
    steps += 1;
    if (visited.has(current) && steps > 2) break; // guard against cycles in preview
  }
  return nodes;
}

function stepsFromNodes(flow: CompiledFlow, nodeIds: string[]): JourneyStep[] {
  return nodeIds
    .map((id) => flow.nodes[id])
    .filter(Boolean)
    .filter((n) => n!.kind !== "Decision" && n!.kind !== "Terminal")
    .map((n) => ({
      id: n!.id,
      kind: n!.kind,
      title: n!.label ?? n!.id,
      // Question nodes may include a prompt for WhatsApp preview
      prompt: (n as unknown as { prompt?: string }).prompt,
    }));
}

export function FlowExperience({ flow }: { flow: CompiledFlow }) {
  const firstDecision = useMemo(() => findFirstBranchDecision(flow), [flow]);
  const branchOptions: BranchOption[] = useMemo(() => {
    if (!firstDecision) return [];
    const outs = sortedOutgoing(flow, firstDecision);
    return outs.map((e) => ({ targetId: e.target, label: pickLabel(e, flow.nodes) }));
  }, [firstDecision, flow]);

  const [selection, setSelection] = useState<Record<string, string>>(() => {
    if (!firstDecision || branchOptions.length === 0) return {};
    return { [firstDecision]: branchOptions[0].targetId };
  });
  
  const [showOnlyCurrentPath, setShowOnlyCurrentPath] = useState(true);
  const [showSidebar, setShowSidebar] = useState(true);

  useEffect(() => {
    if (!firstDecision) return;
    if (!selection[firstDecision] && branchOptions[0]) {
      setSelection({ [firstDecision]: branchOptions[0].targetId });
    }
  }, [firstDecision, branchOptions, selection]);

  const pathNodes = useMemo(() => computePath(flow, selection), [flow, selection]);

  const steps = useMemo(() => stepsFromNodes(flow, pathNodes), [flow, pathNodes]);

  // Convert path to visible and highlighted nodes for React Flow
  const visibleNodes = useMemo(() => {
    if (!showOnlyCurrentPath) return undefined;
    
    // Show ONLY the nodes in the current selected path - much cleaner view
    return new Set(pathNodes);
  }, [pathNodes, showOnlyCurrentPath]);
  const highlightedNodes = useMemo(() => new Set(pathNodes), [pathNodes]);
  
  const highlightedEdges = useMemo(() => {
    const edges = new Set<string>();
    for (let i = 0; i < pathNodes.length - 1; i++) {
      edges.add(`${pathNodes[i]}->${pathNodes[i + 1]}`);
    }
    return edges;
  }, [pathNodes]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-4">
        <div className="space-y-2">
          <div className="text-xl font-bold text-gray-900">
            🤖 {flow.metadata?.name || `Fluxo: ${flow.id}`}
          </div>
          <div className="text-sm text-gray-600">
            {flow.metadata?.description || "Visualize como sua conversa automatizada funciona passo a passo. Cada elemento representa uma etapa na jornada do seu cliente."}
          </div>
        </div>
        
        {/* Quick Tips */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <div className="text-xs text-blue-700 space-y-1">
            <div>🎯 <strong>Layout Inteligente:</strong> Os elementos são organizados automaticamente para minimizar cruzamentos e facilitar a leitura</div>
            <div>💡 <strong>Navegação:</strong> Clique e arraste para mover, use a roda do mouse para zoom</div>
            <div>🔍 <strong>Dica:</strong> Clique em qualquer elemento para ver mais detalhes</div>
            {Object.keys(flow.subflows || {}).length > 0 && (
              <div>🔗 Clique no ícone de link nos subfluxos para navegar</div>
            )}
          </div>
        </div>
      </div>

      {/* Sidebar Toggle (Mobile) */}
      <div className="flex justify-end mb-4 lg:hidden">
        <button
          onClick={() => setShowSidebar(!showSidebar)}
          className="flex items-center gap-2 px-3 py-2 bg-blue-100 text-blue-800 rounded-lg hover:bg-blue-200 transition-colors"
        >
          <span className="text-sm">{showSidebar ? '✕ Ocultar' : '⚙️ Controles'}</span>
        </button>
      </div>

      {/* Main Layout: Graph + Sidebar */}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Graph Visualization */}
        <div className="flex-1">
          <ReactFlowViewer
            flow={flow}
            highlightedNodes={highlightedNodes}
            highlightedEdges={highlightedEdges}
            visibleNodes={visibleNodes}
          />
        </div>
        
        {/* Sidebar */}
        <div className={`w-full lg:w-80 space-y-4 ${!showSidebar ? 'hidden lg:block' : ''}`}>
          {/* Legend */}
          <div className="rounded-xl border bg-card p-4">
            <div className="mb-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm">📊</span>
                <div className="font-medium text-sm">Tipos de Elemento</div>
              </div>
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-blue-200 rounded border border-blue-300"></div>
                <span className="text-xs">
                  <strong>Pergunta</strong> - O que é perguntado ao cliente
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-yellow-200 rounded border border-yellow-300"></div>
                <span className="text-xs">
                  <strong>Decisão</strong> - Como o sistema escolhe o próximo passo
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-green-200 rounded border border-green-300"></div>
                <span className="text-xs">
                  <strong>Finalização</strong> - Fim da conversa
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-purple-200 rounded border border-purple-300"></div>
                <span className="text-xs">
                  <strong>Ação</strong> - Algo executado automaticamente
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-indigo-200 rounded border border-indigo-300"></div>
                <span className="text-xs">
                  <strong>Subfluxo</strong> - Outro fluxo que é executado
                </span>
              </div>
            </div>
          </div>

          {/* View Options */}
          <div className="rounded-xl border bg-card p-4">
            <div className="mb-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm">👁️</span>
                <div className="font-medium text-sm">Visualização</div>
              </div>
            </div>
            <label className="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-gray-50 border border-gray-200 hover:border-gray-300 transition-colors">
              <input
                type="checkbox"
                checked={showOnlyCurrentPath}
                onChange={(e) => setShowOnlyCurrentPath(e.target.checked)}
                className="w-4 h-4 text-blue-600"
              />
              <div className="text-xs">
                <div className="font-medium text-gray-900">Simplificar visualização</div>
                <div className="text-gray-500">Mostra apenas os nós do caminho selecionado</div>
              </div>
            </label>
          </div>

          {/* Path Selection Controls */}
          {firstDecision && branchOptions.length > 0 && (
            <div className="rounded-xl border-2 border-blue-200 bg-blue-50 p-4">
              <div className="mb-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-lg">🎯</span>
                  <div className="font-semibold text-blue-900">Caminho Ativo</div>
                </div>
                <div className="text-xs text-blue-700">
                  Escolha qual caminho você quer visualizar no gráfico
                </div>
              </div>
              <div className="space-y-2">
                {branchOptions.map((option) => (
                  <label key={option.targetId} className="flex items-center gap-3 cursor-pointer p-2 rounded-lg bg-white hover:bg-blue-100 border border-blue-200 hover:border-blue-300 transition-colors">
                    <input
                      type="radio"
                      name="branchSelection"
                      value={option.targetId}
                      checked={selection[firstDecision] === option.targetId}
                      onChange={() => setSelection({ [firstDecision]: option.targetId })}
                      className="w-4 h-4 text-blue-600"
                    />
                    <span className="text-xs font-medium text-blue-900">{option.label}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Flow Stats */}
          <div className="rounded-xl border bg-card p-4">
            <div className="mb-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm">📊</span>
                <div className="font-medium text-sm">Estatísticas do Fluxo</div>
              </div>
            </div>
            <div className="space-y-2 text-xs text-gray-600">
              <div className="flex justify-between">
                <span>Total de elementos:</span>
                <span className="font-medium">{Object.keys(flow.nodes).length}</span>
              </div>
              <div className="flex justify-between">
                <span>Caminho atual:</span>
                <span className="font-medium">{pathNodes.length} passos</span>
              </div>
              {Object.keys(flow.subflows || {}).length > 0 && (
                <div className="flex justify-between">
                  <span>Subfluxos:</span>
                  <span className="font-medium">{Object.keys(flow.subflows || {}).length}</span>
                </div>
              )}
            </div>
          </div>

          {/* WhatsApp Preview */}
          <div className="rounded-xl border-2 border-green-200 bg-green-50 p-4">
            <div className="mb-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm">📱</span>
                <div className="font-semibold text-green-900 text-sm">Prévia WhatsApp</div>
              </div>
              <div className="text-xs text-green-700">
                Como o cliente verá essa conversa
              </div>
            </div>
            <div className="bg-white rounded-lg p-3 border border-green-200 max-h-96 overflow-y-auto">
              <JourneyPreview steps={steps} title="" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}



"use client";

import { useCallback, useMemo, useEffect } from "react";
import {
  ReactFlow,
  useNodesState,
  useEdgesState,
  addEdge,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  ConnectionMode,
  Panel,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";

import { QuestionNode, DecisionNode, TerminalNode, ActionNode, SubflowNode } from "./react-flow-nodes";
import type { CompiledFlow, FlowNodeSummary } from "./types";

// Node type mappings
const nodeTypes = {
  question: QuestionNode,
  decision: DecisionNode,
  terminal: TerminalNode,
  action: ActionNode,
  subflow: SubflowNode,
};

interface ReactFlowViewerProps {
  flow: CompiledFlow;
  highlightedNodes?: Set<string>;
  highlightedEdges?: Set<string>;
  onSubflowClick?: (subflowId: string) => void;
  visibleNodes?: Set<string>;
}

function convertFlowToReactFlow(flow: CompiledFlow, onSubflowClick?: (subflowId: string) => void, visibleNodes?: Set<string>): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  
  // Calculate layout positions using a simple algorithm
  const positions = calculateNodePositions(flow, visibleNodes);
  
  // Create nodes (filter if visibleNodes is specified)
  Object.entries(flow.nodes).forEach(([id, nodeData]) => {
    if (visibleNodes && !visibleNodes.has(id)) return;
    
    const position = positions[id] || { x: 0, y: 0 };
    
    nodes.push({
      id,
      type: nodeData.kind.toLowerCase(),
      position,
      data: {
        ...nodeData,
        isEntry: id === flow.entry,
        onSubflowClick: onSubflowClick,
      },
    });
  });
  
  // Create edges (filter if visibleNodes is specified)
  Object.entries(flow.edges_from).forEach(([sourceId, edgeList]) => {
    if (visibleNodes && !visibleNodes.has(sourceId)) return;
    
    edgeList.forEach((edge, index) => {
      if (visibleNodes && (!visibleNodes.has(edge.source) || !visibleNodes.has(edge.target))) return;
      
              edges.push({
          id: `${edge.source}-${edge.target}-${index}`,
          source: edge.source,
          target: edge.target,
          label: edge.condition_description || edge.label || undefined,
          labelStyle: { fontSize: 12, fontWeight: 500 },
          labelBgPadding: [8, 4],
          labelBgBorderRadius: 4,
          labelBgStyle: { fill: '#ffffff', color: '#374151', fillOpacity: 0.9 },
          type: 'smoothstep', // Use smooth curved edges
          animated: false,
          style: {
            strokeWidth: 2,
            stroke: '#64748b',
          },
          markerEnd: {
            type: 'arrowclosed',
            color: '#64748b',
          },
        });
    });
  });
  
  return { nodes, edges };
}

function calculateNodePositions(flow: CompiledFlow, visibleNodes?: Set<string>): Record<string, { x: number; y: number }> {
  try {
    // Create a new directed graph
    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));
    
    // Only process visible nodes if specified
    const nodeIds = visibleNodes ? 
      Object.keys(flow.nodes).filter(id => visibleNodes.has(id)) : 
      Object.keys(flow.nodes);

    // If no nodes, return empty positions
    if (nodeIds.length === 0) {
      return {};
    }

    // Configure the layout based on graph complexity
    const nodeCount = nodeIds.length;
    const isComplexFlow = nodeCount > 10;
    
    dagreGraph.setGraph({
      rankdir: "TB", // Top to bottom
      nodesep: isComplexFlow ? 120 : 150, // Horizontal space between nodes
      ranksep: isComplexFlow ? 180 : 200, // Vertical space between layers
      edgesep: 30, // Space between edges
      marginx: 60,
      marginy: 60,
    });

    // Add nodes to dagre graph
    nodeIds.forEach(nodeId => {
      const node = flow.nodes[nodeId];
      if (!node) return;
      
      // Set node dimensions based on type (dagre needs these for layout)
      let width = 280;
      let height = 120;
      
      // Adjust size based on node type and content
      if (node.kind === "Decision") {
        width = 300;
        height = 130;
      } else if (node.kind === "Terminal") {
        width = 280;
        height = 120;
      } else if (node.kind === "Question" && (node as any).prompt?.length > 50) {
        height = 140; // Taller for long prompts
        width = 320;
      } else if (node.kind === "Action") {
        width = 290;
        height = 125;
      } else if (node.kind === "Subflow") {
        width = 310;
        height = 135;
      }
      
      // Set special properties for entry node to ensure it's positioned at the top
      const nodeConfig: any = { width, height };
      if (nodeId === flow.entry) {
        nodeConfig.rank = 0; // Ensure entry node is at rank 0 (top)
      }
      
      dagreGraph.setNode(nodeId, nodeConfig);
    });

    // Add edges to dagre graph, ensuring entry node connections are prioritized
    Object.entries(flow.edges_from).forEach(([sourceId, edges]) => {
      if (visibleNodes && !visibleNodes.has(sourceId)) return;
      
      edges.forEach((edge) => {
        if (visibleNodes && (!visibleNodes.has(edge.source) || !visibleNodes.has(edge.target))) return;
        
        let weight = edge.priority !== undefined ? (10 - edge.priority) : 1;
        let minlen = 1;
        
        // Special handling for entry node edges - give them highest priority
        if (edge.source === flow.entry) {
          weight = 0.5; // Very low weight = highest priority
          minlen = 1;
        }
        // Push terminals further down
        else if (flow.nodes[edge.target]?.kind === "Terminal") {
          minlen = 2;
        }
        
        dagreGraph.setEdge(edge.source, edge.target, {
          weight,
          minlen,
        });
      });
    });

    // Run the layout algorithm
    dagre.layout(dagreGraph);

    // Extract positions and ensure entry node is at the top
    const positions: Record<string, { x: number; y: number }> = {};
    let minY = Infinity;
    
    // First pass: get all positions and find the minimum Y
    dagreGraph.nodes().forEach(nodeId => {
      const nodePosition = dagreGraph.node(nodeId);
      const y = nodePosition.y - nodePosition.height / 2;
      minY = Math.min(minY, y);
      positions[nodeId] = {
        x: nodePosition.x - nodePosition.width / 2, // React Flow uses top-left, Dagre uses center
        y: y,
      };
    });
    
    // Second pass: normalize positions so the topmost node starts at y=0
    // and ensure entry node is among the topmost nodes
    const entryNodeY = positions[flow.entry]?.y ?? minY;
    const topMostY = Math.min(minY, entryNodeY);
    
    Object.keys(positions).forEach(nodeId => {
      positions[nodeId].y = positions[nodeId].y - topMostY + 50; // Add small top margin
    });

    return positions;
  } catch (error) {
    console.warn('Dagre layout failed, falling back to simple layout:', error);
    
    // Fallback to simple layout if Dagre fails
    return fallbackLayout(flow, visibleNodes);
  }
}

// Fallback layout function
function fallbackLayout(flow: CompiledFlow, visibleNodes?: Set<string>): Record<string, { x: number; y: number }> {
  const nodeIds = visibleNodes ? 
    Object.keys(flow.nodes).filter(id => visibleNodes.has(id)) : 
    Object.keys(flow.nodes);
    
  const positions: Record<string, { x: number; y: number }> = {};
  
  // Simple grid layout
  nodeIds.forEach((nodeId, index) => {
    const col = index % 3;
    const row = Math.floor(index / 3);
    positions[nodeId] = {
      x: col * 350,
      y: row * 200 + 50,
    };
  });
  
  // Ensure entry node is at top
  if (flow.entry && positions[flow.entry]) {
    positions[flow.entry] = { x: 350, y: 50 };
  }
  
  return positions;
}

function ReactFlowContent({ flow, highlightedNodes, highlightedEdges, onSubflowClick, visibleNodes }: ReactFlowViewerProps) {
  const { fitView, setCenter } = useReactFlow();
  
  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => convertFlowToReactFlow(flow, onSubflowClick, visibleNodes),
    [flow, onSubflowClick, visibleNodes]
  );
  
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  
  // Update nodes and edges when initialNodes/initialEdges change
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  // Center on the topmost/entry node when ready
  useEffect(() => {
    if (initialNodes.length > 0) {
      const timer = setTimeout(() => {
        const hasUserInteracted = sessionStorage.getItem('react-flow-user-interacted');
        if (!hasUserInteracted) {
          // Find the entry node or topmost node
          const entryNode = initialNodes.find(node => node.data.isEntry) || 
                           initialNodes.reduce((topmost, node) => 
                             node.position.y < topmost.position.y ? node : topmost
                           );
          
          if (entryNode) {
            // Center on the entry/topmost node with good zoom
            const centerX = entryNode.position.x + 150; // Add half node width
            const centerY = entryNode.position.y + 80;  // Add half node height
            
            setCenter(centerX, centerY, { 
              zoom: 0.15, 
              duration: 1000 
            });
          }
        }
      }, 300);
      
      return () => clearTimeout(timer);
    }
  }, [initialNodes, setCenter]);
  
  const onConnect = useCallback(
    (params: any) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );
  
  // Apply highlighting
  const highlightedNodesArray = useMemo(() => {
    return nodes.map((node) => ({
      ...node,
      data: {
        ...node.data,
        highlighted: highlightedNodes?.has(node.id),
      },
    }));
  }, [nodes, highlightedNodes]);
  
  const highlightedEdgesArray = useMemo(() => {
    return edges.map((edge) => ({
      ...edge,
      style: {
        ...edge.style,
        stroke: highlightedEdges?.has(`${edge.source}->${edge.target}`) ? '#3b82f6' : '#64748b',
        strokeWidth: highlightedEdges?.has(`${edge.source}->${edge.target}`) ? 3 : 2,
      },
    }));
  }, [edges, highlightedEdges]);

  return (
        <ReactFlow
      nodes={highlightedNodesArray}
      edges={highlightedEdgesArray}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      nodeTypes={nodeTypes}
      connectionMode={ConnectionMode.Strict}
      defaultViewport={{ x: 0, y: 0, zoom: 0.15 }}
      fitView={false}
      fitViewOptions={{
        padding: 0.6,
        includeHiddenNodes: false,
        maxZoom: 2.0,
        minZoom: 0.05,
      }}
      onMoveStart={() => {
        // Mark that user has interacted to prevent auto-fitting
        sessionStorage.setItem('react-flow-user-interacted', 'true');
      }}
      attributionPosition="bottom-left"
      >
        <Controls className="bg-white shadow-lg border" />
        
        {/* Manual fit view button */}
        <Panel position="bottom-right" className="mb-16 mr-2">
          <button
            onClick={() => {
              // Reset to the initial centered view on topmost node
              sessionStorage.removeItem('react-flow-user-interacted');
              
              // Find the entry node or topmost node
              const entryNode = initialNodes.find(node => node.data.isEntry) || 
                               initialNodes.reduce((topmost, node) => 
                                 node.position.y < topmost.position.y ? node : topmost
                               );
              
              if (entryNode) {
                const centerX = entryNode.position.x + 150; // Add half node width
                const centerY = entryNode.position.y + 80;  // Add half node height
                
                setCenter(centerX, centerY, { 
                  zoom: 0.15, 
                  duration: 1000 
                });
              }
            }}
            className="text-xs px-3 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors shadow-lg font-medium"
            title="Resetar a visualização para mostrar todo o fluxo"
          >
            🏠 Reset
          </button>
        </Panel>
        

        <MiniMap 
          className="bg-white shadow-lg border rounded"
          nodeStrokeWidth={1}
          nodeStrokeColor="#64748b"
          style={{ width: 100, height: 60 }}
          nodeColor={(node) => {
            switch (node.type) {
              case 'question': return '#dbeafe';
              case 'decision': return '#fef3c7';
              case 'terminal': return '#dcfce7';
              case 'action': return '#f3e8ff';
              case 'subflow': return '#e0e7ff';
              default: return '#f3f4f6';
            }
          }}
        />
        <Background color="#e2e8f0" gap={16} />
    </ReactFlow>
  );
}

export function ReactFlowViewer(props: ReactFlowViewerProps) {
  return (
    <div className="w-full h-[550px] lg:h-[750px] bg-gradient-to-br from-gray-50 to-gray-100 rounded-xl border-2 border-gray-200 shadow-inner">
      <ReactFlowProvider>
        <ReactFlowContent {...props} />
      </ReactFlowProvider>
    </div>
  );
}




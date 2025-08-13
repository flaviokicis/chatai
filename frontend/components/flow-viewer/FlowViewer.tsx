"use client";

import type { CompiledFlow, EdgeKey } from "./types";
import { computeColumns } from "./layout";
import { NodeCard } from "./NodeCard";
import styles from "./styles.module.css";
import { useRef } from "react";
import { EdgeLayer } from "./EdgeLayer";

export function FlowViewer({
  flow,
  highlightedNodes,
  highlightedEdges,
}: {
  flow: CompiledFlow;
  highlightedNodes?: Set<string>;
  highlightedEdges?: Set<EdgeKey>;
}) {
  const columns = computeColumns(flow);
  const containerRef = useRef<HTMLDivElement>(null!);
  return (
    <div className="relative">
      <div ref={containerRef} className={styles.flowGrid}>
        {columns.map((col) => (
          <div key={col.columnIndex} className={styles.column}>
            {col.nodes.map((n) => (
              <div
                key={n.id}
                data-node-card-id={n.id}
                className={highlightedNodes?.has(n.id) ? styles.nodeCardActiveWrap : undefined}
              >
                <NodeCard node={n} highlighted={highlightedNodes?.has(n.id)} />
              </div>
            ))}
          </div>
        ))}
      </div>
      <EdgeLayer flow={flow} containerRef={containerRef} highlightedEdges={highlightedEdges} />
    </div>
  );
}



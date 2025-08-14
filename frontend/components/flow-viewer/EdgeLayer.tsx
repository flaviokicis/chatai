"use client";

import { useEffect, useMemo, useState } from "react";
import type { CompiledFlow, EdgeKey, MeasuredNodeRect } from "./types";

type NodeAnchor = { id: string; x: number; y: number; width: number; height: number; centerX: number; centerY: number; leftX: number; rightX: number; midY: number };

function measureNodes(container: HTMLElement): MeasuredNodeRect[] {
  const cards = Array.from(container.querySelectorAll<HTMLElement>("[data-node-card-id]"));
  return cards.map((el) => {
    const id = el.getAttribute("data-node-card-id") || "";
    const rect = el.getBoundingClientRect();
    const parentRect = container.getBoundingClientRect();
    return {
      id,
      x: rect.left - parentRect.left + container.scrollLeft,
      y: rect.top - parentRect.top + container.scrollTop,
      width: rect.width,
      height: rect.height,
    };
  });
}

function computeAnchors(rects: MeasuredNodeRect[]): Record<string, NodeAnchor> {
  const anchors: Record<string, NodeAnchor> = {};
  for (const r of rects) {
    anchors[r.id] = {
      id: r.id,
      x: r.x,
      y: r.y,
      width: r.width,
      height: r.height,
      centerX: r.x + r.width / 2,
      centerY: r.y + r.height / 2,
      leftX: r.x,
      rightX: r.x + r.width,
      midY: r.y + r.height / 2,
    };
  }
  return anchors;
}

function computeSvgBounds(rects: MeasuredNodeRect[]): { width: number; height: number } {
  let w = 0;
  let h = 0;
  for (const r of rects) {
    w = Math.max(w, r.x + r.width);
    h = Math.max(h, r.y + r.height);
  }
  return { width: Math.ceil(w + 40), height: Math.ceil(h + 40) };
}

export function EdgeLayer({
  flow,
  containerRef,
  highlightedEdges,
}: {
  flow: CompiledFlow;
  containerRef: React.RefObject<HTMLDivElement>;
  highlightedEdges?: Set<EdgeKey>;
}) {
  const [rects, setRects] = useState<MeasuredNodeRect[]>([]);

  // Re-measure on mount and on resize
  useEffect(() => {
    function doMeasure() {
      if (!containerRef.current) return;
      setRects(measureNodes(containerRef.current));
    }
    doMeasure();
    const ro = new ResizeObserver(doMeasure);
    if (containerRef.current) ro.observe(containerRef.current);
    window.addEventListener("resize", doMeasure);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", doMeasure);
    };
  }, [containerRef]);

  const anchors = useMemo(() => computeAnchors(rects), [rects]);
  const bounds = useMemo(() => computeSvgBounds(rects), [rects]);

  const paths: Array<{ d: string; key: string; active: boolean }> = useMemo(() => {
    const list: Array<{ d: string; key: string; active: boolean }> = [];
    for (const [src, edges] of Object.entries(flow.edges_from)) {
      edges.forEach((e, idx) => {
        const a = anchors[src];
        const b = anchors[e.target];
        if (!a || !b) return;

        // Route edges left-to-right from the right mid of source to the left mid of target
        const sx = a.rightX;
        const sy = a.midY;
        const tx = b.leftX;
        const ty = b.midY;
        const dx = Math.max(48, Math.abs(tx - sx) / 2);
        const d = `M ${sx} ${sy} C ${sx + dx} ${sy}, ${tx - dx} ${ty}, ${tx} ${ty}`;
        const keyBase = `${e.source}->${e.target}` as EdgeKey;
        const k = `${keyBase}#${e.priority ?? 0}#${idx}`;
        list.push({ d, key: k, active: highlightedEdges?.has(keyBase) ?? false });
      });
    }
    return list;
  }, [anchors, flow.edges_from, highlightedEdges]);

  return (
    <svg width={bounds.width} height={bounds.height} className="pointer-events-none absolute inset-0">
      <defs>
        <linearGradient id="edgeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="hsl(var(--muted-foreground))" stopOpacity="0.4" />
          <stop offset="100%" stopColor="hsl(var(--muted-foreground))" stopOpacity="0.8" />
        </linearGradient>
        <marker id="arrow" markerWidth="10" markerHeight="10" refX="10" refY="5" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="hsl(var(--muted-foreground))" />
        </marker>
      </defs>
      {paths.map((p) => (
        <path
          key={p.key}
          d={p.d}
          fill="none"
          stroke={p.active ? "hsl(var(--primary))" : "url(#edgeGradient)"}
          strokeWidth={p.active ? 2.5 : 1.5}
          opacity={p.active ? 0.95 : 0.7}
          markerEnd="url(#arrow)"
        />
      ))}
    </svg>
  );
}



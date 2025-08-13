"use client";

import type { PositionedNode } from "./types";
import styles from "./styles.module.css";

function KindBadge({ kind }: { kind: string }) {
  const cls =
    kind === "Question" ? styles.qBadge : kind === "Decision" ? styles.dBadge : styles.tBadge;
  return <span className={`${styles.badge} ${cls}`}>{kind}</span>;
}

export function NodeCard({ node, highlighted, variant = "default" }: { node: PositionedNode; highlighted?: boolean; variant?: "default" | "compact" }) {
  const showMeta = variant === "default";
  return (
    <div className={`${styles.nodeCard} ${highlighted ? styles.nodeCardActive : ""} ${variant === "compact" ? styles.nodeCardCompact : ""}`}>
      <div className={styles.nodeHeader}>
        <div className={variant === "compact" ? styles.nodeTitle : "font-medium truncate"}>
          {node.kind === "Question" && (node as any).prompt ? (node as any).prompt : node.label ?? node.id}
        </div>
        <KindBadge kind={node.kind} />
      </div>
      {showMeta ? (
        <div className={styles.meta}>
          <div>ID: {node.id}</div>
          {node.isEntry ? <div>Entry</div> : null}
        </div>
      ) : null}
      {variant === "default" && node.kind === "Question" && (node as any).prompt ? (
        <div className={styles.prompt}>
          <div className={styles.promptTitle}>Prompt</div>
          <div className={styles.promptBody}>{(node as any).prompt}</div>
        </div>
      ) : null}
      {variant === "default" ? (
      <div className={styles.outgoing}>
        <div className={styles.outgoingTitle}>Outgoing</div>
        <ul className={styles.outgoingList}>
          {node.outgoing.map((e, i) => (
            <li key={`${e.source}->${e.target}#${e.priority ?? 0}#${i}`}>
              {e.label ? <span className={styles.edgeLabel}>{e.label}</span> : null}
              {e.target}
              {e.condition_description ? (
                <span className={styles.edgeCond}> – {e.condition_description}</span>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
      ) : null}
    </div>
  );
}


